from __future__ import division, print_function
import sys
import datetime
from os import path
from functools import partial
from configparser import ConfigParser
from itertools import takewhile

from qtpy import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

import csapi
from gage_widgets import ChannelWidget, SlotHandler, TriggerDialog, RunWidget
import gage_util
from gage_util import GageMode, GageState, ChannelConfig, HeterodyneFilter, DecimateFilter, get_script_path, log
from gage_workers import GageCapture, GageSegWorker, GageTradWorker

gage_util.print_level = 2
pg.setConfigOptions(antialias=True, useWeave=True)


def allnamesequal(name):
    return all(n == name[0] for n in name[1:])


def commonpath(paths, sep='/'):
    bydirectorylevels = zip(*[p.split(sep) for p in paths])
    return sep.join(x[0] for x in takewhile(allnamesequal, bydirectorylevels))


path.commonpath = commonpath

"""
configuration
"""

dataRoot = 'Y:\\expdata-e6\\data\\'
analysisRoot = 'Y:\\expdata-e6\\data\\'

try:
    csapi.Initialize()
except Exception as err:
    print('Failed to initialize GageScope API: ', err)

sample_clk = 200e6
ext_clk = 200e6
carrier_freq = 15e6

trigger_config = (csapi.TriggerSource.EXT, csapi.Coupling.DC, csapi.Impedance.Z_1M, csapi.Gain.G_10Vpp)

heterodyne = ChannelConfig(1, csapi.Coupling.DC, csapi.Impedance.Z_50, csapi.Gain.G_4Vpp, name='Heterodyne')
heterodyne.filter = HeterodyneFilter(carrier_freq, bw=20e3, max_length=200e3)
heterodyne.pen = (pg.mkPen('b', width=1), pg.mkPen('r', width=1))

vco = ChannelConfig(2, csapi.Coupling.DC, csapi.Impedance.Z_1M, csapi.Gain.G_2Vpp, resample=2e6, name='VCO')
vco.filter = DecimateFilter(10, max_length=200e3)
# vco.pen = pg.mkPen('g', width=1)
vco.pen = (pg.mkPen('g', width=1), pg.mkPen('r', width=1))

odt = ChannelConfig(3, csapi.Coupling.DC, csapi.Impedance.Z_1M, csapi.Gain.G_2Vpp, resample=2e6, name='ODT')
odt.filter = DecimateFilter(10, max_length=200e3)
# odt.pen = pg.mkPen('y', width=1)
odt.pen = (pg.mkPen('y', width=1), pg.mkPen('r', width=1))

channel_config = (heterodyne, vco)


class GageDummy(object):
    def __init__(self):
        pass

    def null(self, *args, **kwargs):
        pass

    def __getattr__(self, key):
        return self.null


# TODO add out of range warnings!


class GageWindow(QtWidgets.QMainWindow):
    gage = None

    mode_changed = QtCore.Signal(GageMode)
    state_changed = QtCore.Signal(GageState)
    triggers_changed = QtCore.Signal(list)

    capture_acquired = QtCore.Signal(GageCapture)

    config_file = None

    def __init__(self, parent=None):
        super(GageWindow, self).__init__(parent)

        self.sample_length = 12.0

        self._mode = GageMode.SEG
        self._state = GageState.IDLE
        self._acquiring = False

        self.triggers = [('', 0)]

        self.history = []

        self.setupMenu()
        self.setupUi()

        self._thread = None
        self._worker = None

        try:
            self.gage = csapi.System(reset=False)
        except Exception as e:
            print('Error opening GageScope: ', e)
            print('Continuing in debug mode')
            self.gage = GageDummy()

        self.info = self.gage.GetInfo()

        self.gage.RegisterCallback(csapi.AcquisitionEvent.END_BUSY, self.on_acquired)

        self.mode = GageMode.SEG

        self.settings_file = path.join(get_script_path(), 'gage.set')
        self.load_settings()
        if len(self.history) > 0:
            self._load_config(self.history[0])

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, value):
        self._mode = value
        self.mode_changed.emit(self._mode)

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value
        self.state_changed.emit(self._state)

    def closeEvent(self, event):
        self._stop_acquisition()

        self.gage.Close()
        self.gage = None
        self.save_settings()

    def load_settings(self):
        if self._acquiring:
            print('Cannot load settings file while acquiring')
            return

        settings = ConfigParser()
        settings.read(self.settings_file)

        if settings.has_section('History'):
            self.history = [value for key, value in sorted(settings.items('History'))]
        else:
            self.history = []

        self._update_history_menu()

    def save_settings(self):
        settings = ConfigParser()

        settings.add_section('History')

        for idx, value in enumerate(self.history):
            settings.set('History', 'config{:d}'.format(idx), value)

        with open(self.settings_file, 'w') as cf:
            settings.write(cf)

    def _push_history(self, filename, max_history=10):
        self.history.insert(0, filename)
        # remove duplicate values, but keep order

        self.history = [x for i, x in enumerate(self.history) if self.history.index(x) == i]
        if len(self.history) > max_history:
            self.history = self.history[:max_history]
        self._update_history_menu()

    def _update_history_menu(self):

        self.history_menu.clear()

        basename = path.commonpath(self.history)

        for idx, item in enumerate(self.history):
            label = path.relpath(item, basename)
            action = QtWidgets.QAction("{:d}: {:s}".format(idx, label), self)
            action.setStatusTip(item)
            action.triggered.connect(partial(self._load_config, item))
            self.history_menu.addAction(action)

    def _save_config(self, filename):

        config = ConfigParser()
        config.add_section('Global')
        config.set('Global', 'mode', self.mode.name)

        if self.mode == GageMode.TRAD:
            config.set('Global', 'length', '{:.1f}'.format(self.length_input.value()))
        else:
            config.add_section('Triggers')

            for idx, trigger in enumerate(self.triggers):
                value = '{:s},{:.1f}'.format(*trigger)
                config.set('Triggers', 'trigger{:d}'.format(idx), value)

            for channel in channel_config:
                cw = self.channel_widgets[channel.id]
                channel.segments = cw.get_segments()
                channel.save_config(config)

        with open(filename, 'w') as cf:
            config.write(cf)

        self._push_history(filename)

    def _load_config(self, filename):
        if self._acquiring:
            print('Cannot load config file while acquiring')
            return

        print('Loading config file ''{}'''.format(filename))

        try:
            config = ConfigParser()
            config.read(filename)

            if config.has_option('Global', 'mode'):
                mode = config.get('Global', 'mode')
                try:
                    self.mode = GageMode[mode]
                except Exception as e:
                    print('Invalid mode', e)

            if config.has_option('Global', 'length'):
                length = config.get('Global', 'length')
                try:
                    self.length_input.setValue(float(length))
                except Exception as e:
                    print('Invalid length', e)

            if config.has_section('Triggers'):
                self.triggers = []
                for key, data in config.items('Triggers'):
                    prefix, timeout = data.split(",")
                    self.triggers.append((prefix, float(timeout)))

                self.trigger_button.setText('Triggers: {}'.format(len(self.triggers)))
                self.triggers_changed.emit(self.triggers)

            for channel in channel_config:
                channel.load_config(config)
                cw = self.channel_widgets[channel.id]
                cw.set_segments(channel.segments)

            self.config_file = filename
            self._push_history(filename)
        except Exception as e:
            print('Error reading config file: ', e)

    def menu_exit(self):
        self.close()

    def menu_open(self):
        if self._acquiring:
            return

        filename = QtWidgets.QFileDialog.getOpenFileName(self, "Save Configuration", "",
                                                         "Configuration files (*.cfg);; All Files (*)")
        if isinstance(filename, tuple):  # Qt4/5 compatibility
            filename = filename[0]

        if filename == '':
            return

        self._load_config(filename)

    def menu_save(self):

        if self.config_file is None:
            filename = QtWidgets.QFileDialog.getSaveFileName(self, "Save Configuration", "",
                                                             "Configuration files (*.cfg);; All Files (*)")
            if isinstance(filename, tuple):  # Qt4/5 compatibility
                filename = filename[0]

            if filename == '':
                return

            self.config_file = filename

        self._save_config(self.config_file)

    def menu_saveas(self):
        filename = QtWidgets.QFileDialog.getSaveFileName(self, "Save Configuration", "",
                                                         "Configuration files (*.cfg);; All Files (*)")
        if isinstance(filename, tuple):  # Qt4/5 compatibility
            filename = filename[0]

        if filename == '':
            return

        self.config_file = filename
        self._save_config(self.config_file)

    def menu_trad(self):
        if self._acquiring:
            return

        self.mode = GageMode.TRAD

    def menu_seg(self):
        if self._acquiring:
            return

        self.mode = GageMode.SEG

    def setupMenu(self):

        self.statusBar()
        main_menu = self.menuBar()

        file_items = [
            ("&Load", 'Ctrl+O', 'Open saved configuration.', self.menu_open),
            ("&Save", 'Ctrl+S', 'Save the current configuration.', self.menu_save),
            ("Save &as...", 'Ctrl+Shift+S', 'Save the current configuration as...', self.menu_saveas),
            None,
            ("&Exit", 'Ctrl+Q', 'Stop acquisition and close the application.', self.menu_exit)
        ]

        self.file_menu = main_menu.addMenu("&File")
        for item in file_items:
            if item is None:
                self.file_menu.addSeparator()
                continue

            (name, shortcut, tip, slot) = item
            action = QtWidgets.QAction(name, self)
            if shortcut is not None:
                action.setShortcut(shortcut)
            action.setStatusTip(tip)
            action.triggered.connect(slot)
            self.file_menu.addAction(action)

        self.history_menu = main_menu.addMenu("&History")

        mode_items = [
            ("&Traditional (*.sig)", None, 'GageScope compatible signal acquisition, saved to *.sig files.',
             self.menu_trad),
            ("&Segmented (*.h5)", None, 'Segmented signal acquisition, saved to *.h5 files.', self.menu_seg),
        ]

        self.mode_menu = main_menu.addMenu("&Mode")
        mode_group = QtWidgets.QActionGroup(self)
        for item in mode_items:
            (name, shortcut, tip, slot) = item
            action = QtWidgets.QAction(name, self)
            if shortcut is not None:
                action.setShortcut(shortcut)
            action.setStatusTip(tip)
            action.setCheckable(True)
            action.triggered.connect(slot)
            mode_group.addAction(action)
            self.mode_menu.addAction(action)

        action.setChecked(True)

    def setupUi(self):
        self.setWindowTitle("Gage Acquire")
        self.centralWidget = QtWidgets.QWidget()
        self.setCentralWidget(self.centralWidget)
        self.resize(1024, 768)

        layout = QtWidgets.QVBoxLayout()

        acquisition_layout = QtWidgets.QHBoxLayout()

        self.start_button = QtWidgets.QPushButton('Start Acquisition')
        self.start_button.setCheckable(True)
        self.start_button.clicked.connect(self.toggleStart)

        self.length_input = self.floatSpinBox()

        self.trigger_button = QtWidgets.QPushButton('Triggers: {:d}'.format(len(self.triggers)))
        self.trigger_button.clicked.connect(self.edit_triggers)
        self.trigger_button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        acquisition_layout.addWidget(self.start_button)
        self.length_label = QtWidgets.QLabel('Length: ')
        self.length_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        acquisition_layout.addWidget(self.length_label)
        acquisition_layout.addWidget(self.length_input)
        acquisition_layout.addWidget(self.trigger_button)

        layout.addLayout(acquisition_layout)

        self.channel_widgets = {}
        for channel in channel_config:
            cw = ChannelWidget(channel)
            self.channel_widgets[channel.id] = cw

            layout.addWidget(cw)

            self.mode_changed.connect(cw.on_mode_changed)
            self.state_changed.connect(cw.on_state_changed)
            self.triggers_changed.connect(cw.set_triggers)

        self.run_widget = RunWidget(dataRoot, analysis_root=analysisRoot, mode=self.mode)
        self.run_widget.status.connect(self.run_status)
        # self.mode_changed.connect(self.run_widget.mode_changed)
        self.run_widget.setEnabled(False)

        layout.addWidget(self.run_widget)
        self.centralWidget.setLayout(layout)

        self.mode_changed.connect(self.on_mode_changed)
        self.state_changed.connect(self.on_state_changed)

    def floatSpinBox(self):
        widget = QtWidgets.QDoubleSpinBox()
        widget.setDecimals(1)
        widget.setRange(1, 200)
        widget.setDecimals(1)
        widget.setSuffix(' ms')
        widget.setValue(self.sample_length)
        widget.setFixedWidth(100)
        return widget

    def on_mode_changed(self, mode):
        self.run_widget.mode = mode

        if mode == GageMode.TRAD:
            self.trigger_button.setVisible(False)

            self.length_label.setVisible(True)
            self.length_input.setVisible(True)
        else:
            self.trigger_button.setVisible(True)

            self.length_label.setVisible(False)
            self.length_input.setVisible(False)

            self.triggers_changed.emit(self.triggers)

    @SlotHandler
    def toggleStart(self, checked):
        if self.start_button.isChecked():
            self.start_button.setText('Starting...')

            if self.mode == GageMode.TRAD:
                self.sample_length = self.length_input.value()
                for config in channel_config:
                    config.segments = []

                self._worker = GageTradWorker(self.run_widget)

            elif self.mode == GageMode.SEG:
                self.sample_length = 0
                for config in channel_config:
                    cw = self.channel_widgets[config.id]
                    config.segments = cw.get_segments()

                    seg_ends = [seg[2] for seg in config.segments]
                    if len(seg_ends) > 0:
                        self.sample_length = max(self.sample_length, max(seg_ends))

                self._worker = GageSegWorker(self.run_widget, self.triggers)

            self.sample_depth = int(sample_clk * self.sample_length / 1e3)

            for cid, cw in self.channel_widgets.items():
                cw._pw.setXRange(0, self.sample_length * 1e-3)

            log('Starting acquisition for {:.1f} ms ({:d} samples)'.format(self.sample_length, self.sample_depth))
            self._gage_configure()

            self._thread = QtCore.QThread()
            self._worker.moveToThread(self._thread)
            self.capture_acquired.connect(self._worker.process_capture)
            self._worker.plot_capture.connect(self._plot_capture)

            self._thread.started.connect(self._worker.started)
            self._thread.finished.connect(self._thread_finished)

            self._thread.start()

            self._acquiring = True
            self.gage.Start()  # Arm acquisition
            self.state = GageState.ACQUIRE
        else:
            self._stop_acquisition()

    def _stop_acquisition(self):
        self._acquiring = False
        self.start_button.setText('Stopping...')
        self.gage.Abort()  # Abort acquisition

        if self._thread is not None:
            # TODO make sure this doesn't ignore data in the Event queue!!
            self._thread.quit()

        self.state = GageState.IDLE
        log('Acquisition stopped')

    def _thread_finished(self):
        log('Worker thread finished', 5)
        # Manually disconnect this signal, otherwise it somehow remains connected within Qt, and the GageCapture objects
        # queue up in the void somewhere on the defunct worker object/thread, causing a memory leak
        self.capture_acquired.disconnect(self._worker.process_capture)
        self._worker.deleteLater()
        self._worker = None
        self._thread.deleteLater()
        self._thread = None

    def _gage_configure(self):
        self.gage.SetAcquisition(
            sample_rate=int(sample_clk),
            extclk=int(ext_clk),
            mode=csapi.Mode.DUAL,
            segment_count=1,
            depth=self.sample_depth,
            trigger_timeout=-1,  # Set to CS_TIMEOUT_DISABLE=-1
            segment_size=self.sample_depth
        )

        for channel in channel_config:
            self.gage.SetChannel(channel.id,
                                 term=channel.coupling,
                                 impedance=channel.impedance,
                                 input_range=channel.range,  # in [mV]
                                 )

        (source, coupling, imped, range) = trigger_config
        self.gage.SetTrigger(
            condition=1,  # Rising slope
            ext_trigger_range=range,  # Vpp range in [mV]
            ext_impedance=imped,  # in Ohms
            ext_coupling=coupling,  # DC coupling
            source=source,
            level=30  # Percentage of range/2
        )

        self.gage.Commit()

    def on_state_changed(self, state):
        if state == GageState.IDLE:
            self.start_button.setText('Start Acquisition')
            self.length_input.setEnabled(True)
            self.trigger_button.setEnabled(True)
            self.run_widget.setEnabled(False)

            for action in self.mode_menu.actions():
                action.setEnabled(True)
            for action in self.history_menu.actions():
                action.setEnabled(True)

        else:
            self.start_button.setText('Acquiring')
            self.length_input.setEnabled(False)
            self.trigger_button.setEnabled(False)
            self.run_widget.setEnabled(True)

            for action in self.mode_menu.actions():
                action.setEnabled(False)
            for action in self.history_menu.actions():
                action.setEnabled(False)

    @SlotHandler
    def edit_triggers(self, checked):
        dialog = TriggerDialog(self.triggers, parent=self)

        def save_triggers():
            self.triggers = dialog.get_triggers()
            self.triggers_changed.emit(self.triggers)
            self.trigger_button.setText('Triggers: {}'.format(len(self.triggers)))

        dialog.accepted.connect(save_triggers)
        dialog.show()

    def run_status(self, running):
        runname = self.run_widget.getRunname()
        if running:
            log('Run ''{}'' started'.format(runname))
            self.start_button.setEnabled(False)
        else:
            log('Run ''{}'' stopped'.format(runname))
            self.start_button.setEnabled(True)

    def on_acquired(self, cbInfo):
        timestamp = datetime.datetime.now()

        if not self._acquiring:
            return

        log('Acquired', 3)

        capture = GageCapture(channel_config, timestamp)
        capture.download(self.gage)

        log('Downloaded', 4)

        self.gage.Start()  # Re-arm acquisition

        self.capture_acquired.emit(capture)

    def _plot_capture(self, plot_data, line):
        # This slot is triggered by the plot_capture signal in the Worker, and plots each capture in the UI thread
        # after processing is finished
        log('Start plotting', 6)

        for cid, widget in self.channel_widgets.items():
            if cid not in plot_data:
                continue

            filt_time, filt_data = plot_data[cid]
            widget.plot(filt_time, filt_data, line=line)

        log('Finished plotting', 6)


# Start Qt event loop unless running in interactive mode.
def main():
    try:
        import ctypes
        myappid = u'ultracold.gage_acquire'  # arbitrary string
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon('favicon.ico'))
    ex = GageWindow()
    ex.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
