from __future__ import division,print_function
from functools import wraps
import traceback
import datetime
from os import makedirs, path

from qtpy import QtCore, QtGui, QtWidgets

import pyqtgraph as pg
from gage_util import GageMode,GageState

def SlotHandler(func):
	@wraps(func)
	def wrapper(*args, **kwargs):
		try:
			func(*args, **kwargs)
		except:
			print("Uncaught Exception in slot")
			traceback.print_exc()
	return wrapper
		
class ChannelWidget(QtWidgets.QWidget):
	
	def __init__(self, config, plot_config = None, segments=[], parent=None):
		super(ChannelWidget, self).__init__(parent)
		
		self.config = config
		self.plot_config = plot_config

		self.lines = {}
		self.segment_region = {}
			
		self.setupUi(segments)
		
	def setupUi(self, segments=None):
		self._pw = pg.PlotWidget()
						
		plot_item = self._pw.getPlotItem()
		plot_item.setLabel('bottom', text='Time', units='s')
		plot_item.setLabel('left', text='Signal', units='V')
		
		self._leg = None
		self._update_lines(1)
		
		self.segment_widget = SegmentWidget(self.config, segments)
		self.segment_widget.table.changed.connect(self._update_segments)
		
		if segments is not None:
			self._update_segments(segments)
		
		layout = QtWidgets.QHBoxLayout()
		layout.addWidget(self._pw)
		layout.addWidget(self.segment_widget)
		
		self.setLayout(layout)
		
	def on_mode_changed(self, mode):
		if mode == GageMode.TRAD:
			self.segment_widget.setVisible(False)
			for idx,region in self.segment_region.items():
				region.setVisible(False)
			self._update_lines(1)
		else:
			self.segment_widget.setVisible(True)
			for idx,region in self.segment_region.items():
				region.setVisible(True)
			
	def on_state_changed(self, mode):
		if mode == GageState.IDLE:
			self.segment_widget.setEnabled(True)
		else:
			self.segment_widget.setEnabled(False) 
		
	def get_segments(self):
		return self.segment_widget.table.get_segments()
	
	def set_segments(self, segments):
		self.segment_widget.table.set_segments(segments)
		
	def set_triggers(self, triggers):
		self._update_lines(len(triggers))
		
	def _update_lines(self, num):
		plot_item = self._pw.getPlotItem()
		
		if num > len(self.lines):
			for idx in range(len(self.lines), num):
				self.lines[idx] = pg.PlotDataItem(pen=self.config.get_pen(idx))
				plot_item.addItem(self.lines[idx])
		elif num < len(self.lines):
			for idx in range(num, len(self.lines)):
				plot_item.removeItem(self.lines[idx])
				del self.lines[idx]

		# Remove and recreate legend. Adding and removing items in legend is too buggy in pyqtgraph-0.10.0
		if self._leg is not None:
			plot_item.scene().removeItem(self._leg)
		self._leg = plot_item.addLegend(size=(100, 40), offset=(-20, 20))
		for idx in range(0,num):
			self._leg.addItem(self.lines[idx], self.config.name)
			
		
	def _update_segments(self, segments):
		self._create_segment_regions(len(segments))
		for idx,values in enumerate(segments):
			name, start, stop = values
			self.segment_region[idx].setRegion((start/1000, stop/1000)) #convert to ms

	def _create_segment_regions(self, num):
		plot_item = self._pw.getPlotItem()

		pen = pg.mkPen(color=(200, 200, 255, 100))
		brush = pg.mkBrush(color=(200, 200, 255, 50))

		if num > len(self.segment_region):
			for idx in range(len(self.segment_region), num):
				self.segment_region[idx] = pg.LinearRegionItem(movable=False, brush=brush)
				for line in self.segment_region[idx].lines:
					line.setPen(pen)
				
				plot_item.addItem(self.segment_region[idx])
		elif num < len(self.segment_region):
			for idx in range(num, len(self.segment_region)):
				plot_item.removeItem(self.segment_region[idx])
				del self.segment_region[idx]

	def plot(self, t, data, line=0):
		self.lines[line].setData(t, data)


class SegmentWidget(QtWidgets.QWidget):
		
	def __init__(self, channel, segments=None, parent=None, show_add=False):
		super(SegmentWidget, self).__init__(parent)
		
		self.channel = channel
		
		if segments is None:
			segments = [('channel{:1d}'.format(self.channel.id), 0.0, 2.0)];
			
		self.segments = segments
		
		self.show_add = show_add
		
		self.setupUi()


	def setupUi(self):
		
		self.setFixedWidth(300)
		layout = QtWidgets.QVBoxLayout()
		
		self.table = SegmentTable(self.segments)
		layout.addWidget(self.table)
		
		if self.show_add:
			self.add = QtWidgets.QPushButton('Add Segment')
			self.add.clicked.connect(self.table.addSegment)	
			layout.addWidget(self.add)
		
		self.setLayout(layout)
		
		
	
class SegmentTable(QtWidgets.QTableWidget):
		
	changed = QtCore.Signal(list)
	
	def __init__(self, segments=None, parent=None):
		super(SegmentTable, self).__init__(parent)
			
		self.setupUi()
		
		for segment in segments:
			self.addSegment(*segment)		


	def setupUi(self):
		
		self.setColumnCount(3)
			
		self.verticalHeader().setDefaultSectionSize(24);
		
		header = self.horizontalHeader()
		header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
		header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
		header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)

		self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
		self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)  			
		
		self.setHorizontalHeaderLabels (['Name','Start (ms)','Stop (ms)'])

	@SlotHandler
	def contextMenuEvent(self, event):
		row = self.rowAt(event.pos().y())
		col = self.columnAt(event.pos().x())
		
		self.menu = QtWidgets.QMenu(self)
		
		#TODO: rewrite without lambda functions. The lambda stores a reference to 'self', which might prevent proper garbage collection of self
		if row < 0:
			addAction = QtWidgets.QAction('Add Segment', self)
			addAction.triggered.connect(lambda: self.addSegment())
			self.menu.addAction(addAction)			
		else:
			item = self.item(row, 0)
			name = item.text() if item is not None else ''
			
			aboveAction = QtWidgets.QAction('Insert Above', self)
			aboveAction.triggered.connect(lambda: self.addSegment(pos=row))
			self.menu.addAction(aboveAction)

			belowAction = QtWidgets.QAction('Insert Below', self)
			belowAction.triggered.connect(lambda: self.addSegment(pos=row+1))
			self.menu.addAction(belowAction)
			
			deleteAction = QtWidgets.QAction('Delete "{}"'.format(name), self)
			deleteAction.triggered.connect(lambda: self.removeSegment(row))
			self.menu.addAction(deleteAction)
		
		self.menu.popup(QtGui.QCursor.pos())

	@SlotHandler
	def addSegment(self, name='', start=0.0, stop=10.0, pos=-1):
		if pos == -1:
			pos = self.rowCount()
			
		self.insertRow(pos)
		
		item = QtWidgets.QTableWidgetItem(name)
		self.setItem(pos, 0, item)

		start_input = self.floatSpinBox()
		start_input.setValue(start)
		start_input.valueChanged.connect(self._changed)
		self.setCellWidget(pos, 1, start_input)
		
		stop_input = self.floatSpinBox()
		stop_input.setValue(stop)
		stop_input.valueChanged.connect(self._changed)
		self.setCellWidget(pos, 2, stop_input)
		
		self._changed()
		
	def _changed(self):
		segments = self.get_segments()
		self.changed.emit(segments)
		
	def get_segments(self):
		return [self.getSegment(row) for row in range(0, self.rowCount())]
		
	def getSegment(self, row):
		
		item = self.item(row, 0)
		name = item.text() if item is not None else ''
		
		start = self.cellWidget(row, 1)
		stop = self.cellWidget(row, 2)

		return (name, start.value(), stop.value())	
		
	def set_segments(self, segments):
		self.setRowCount(0)

		for segment in segments:
			self.addSegment(*segment)
		
		self.changed.emit(segments)
	
	def removeSegment(self, index):
		self.removeRow(index)
		self._changed()
	
	def floatSpinBox(self):
		widget = QtWidgets.QDoubleSpinBox()
		widget.setDecimals(1)
		widget.setRange(0,999)
		widget.setDecimals(1)
		#widget.setFixedWidth(70)
		return widget		
		
		
class TriggerDialog(QtWidgets.QDialog):
		
	def __init__(self, triggers=None, parent=None):
		super(TriggerDialog, self).__init__(parent)
		
		if triggers is None:
			triggers = [('', 0)]
		
		self.setupUi(triggers)
		
		self.setModal(True)
		self.setWindowTitle ('Configure Triggers')
				
	def setupUi(self, triggers):

		layout = QtWidgets.QVBoxLayout()

		self.table = TriggerTable(triggers)
		
		self.add = QtWidgets.QPushButton('Add Trigger')
		self.add.clicked.connect(self.table.add_trigger)
		
		self.buttonBox = QtWidgets.QDialogButtonBox()
		self.buttonBox.addButton("Apply", QtWidgets.QDialogButtonBox.AcceptRole)
		self.buttonBox.addButton("Cancel", QtWidgets.QDialogButtonBox.RejectRole)
		
		self.buttonBox.accepted.connect(self.accept)
		self.buttonBox.rejected.connect(self.reject)		
		
		layout.addWidget(self.add)
		layout.addWidget(self.table)
		layout.addWidget(self.buttonBox)
		
		self.setLayout(layout)
		
	def get_triggers(self):
		return self.table.get_triggers()
	

class TriggerTable(QtWidgets.QTableWidget):
		
	def __init__(self, triggers=None, parent=None):
		super(self.__class__, self).__init__(parent)
			
		self.setupUi()
		
		for trigger in triggers:
			self.add_trigger(*trigger)		


	def setupUi(self):
		
		self.setColumnCount(2)
			
		self.verticalHeader().setDefaultSectionSize(24);
		
		header = self.horizontalHeader()
		header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
		header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)

		self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
		self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)  			
		
		self.setHorizontalHeaderLabels (['Prefix','Timeout (s)'])

	@SlotHandler
	def contextMenuEvent(self, event):
		row = self.rowAt(event.pos().y())

		self.menu = QtWidgets.QMenu(self)
		
		#TODO: rewrite without lambda functions. The lambda stores a reference to 'self', which might prevent proper garbage collection of self
		if row < 0:
			addAction = QtWidgets.QAction('Add Trigger', self)
			addAction.triggered.connect(lambda: self.add_trigger())
			self.menu.addAction(addAction)			
		else:
			item = self.item(row, 0)
			name = item.text() if item is not None else ''
			
			aboveAction = QtWidgets.QAction('Insert Above', self)
			aboveAction.triggered.connect(lambda: self.add_trigger(pos=row))
			self.menu.addAction(aboveAction)

			belowAction = QtWidgets.QAction('Insert Below', self)
			belowAction.triggered.connect(lambda: self.add_trigger(pos=row+1))
			self.menu.addAction(belowAction)
			
			if self.rowCount() > 1:
				deleteAction = QtWidgets.QAction('Delete "{}"'.format(name), self)
				deleteAction.triggered.connect(lambda: self.remove_trigger(row))
				self.menu.addAction(deleteAction)
			
		self.menu.popup(QtGui.QCursor.pos())
	
	@SlotHandler
	def add_trigger(self, prefix='', timeout=3.0, pos=-1):
		if pos == -1:
			pos = self.rowCount()
		self.insertRow(pos)
		
		item = QtWidgets.QTableWidgetItem(prefix)
		self.setItem(pos, 0, item)

		timeout_input = self.floatSpinBox()
		timeout_input.setValue(timeout)
		self.setCellWidget(pos, 1, timeout_input)
		
	def get_triggers(self):
		return [self.get_trigger(row) for row in range(0, self.rowCount())]
		
	def get_trigger(self, row):
		
		item = self.item(row, 0)
		name = item.text() if item is not None else ''
		
		timeout = self.cellWidget(row, 1)

		return (name, timeout.value())	
		
	def set_triggers(self, triggers):
		self.setRowCount(0)

		for trigger in triggers:
			self.add_trigger(*trigger)		
	
	def remove_trigger(self, index):
		self.removeRow(index)
	
	def floatSpinBox(self):
		widget = QtWidgets.QDoubleSpinBox()
		widget.setDecimals(1)
		widget.setRange(0,999)
		widget.setDecimals(1)
		#widget.setFixedWidth(70)
		return widget
		

class RunWidget(QtWidgets.QWidget):
	
	status = QtCore.Signal(bool)
	incremented = QtCore.Signal(int)
	
	def __init__(self, data_root, analysis_root=None, mode=GageMode.TRAD, parent=None):
		super(RunWidget, self).__init__(parent)
		self.data_root = data_root
		self.analysis_root = analysis_root
		self.mode = mode
		
		self.cur_file = 0
		self.running = False
		
		self.setupUi()
		
	def setupUi(self):
		
		today = datetime.date.today()
		self.run_date = QtWidgets.QLineEdit('{date:%Y\\%m\\%d}'.format(date=today))
		self.run_name = QtWidgets.QLineEdit('run0')
		
		self.run_file = QtWidgets.QSpinBox()
		self.run_file.setMinimum(0)
		self.run_file.setMaximum(10000)
		self.run_file.setValue(self.cur_file)
		
		self.start_button = QtWidgets.QPushButton('Start')
		self.start_button.setCheckable(True)
		self.start_button.setChecked(self.running)
		verticalLayout = QtWidgets.QVBoxLayout()
		layout = QtWidgets.QHBoxLayout()

		layout.addWidget(QtWidgets.QLabel('Data root:'))
		layout.addWidget(QtWidgets.QLabel(self.data_root))
		layout.addWidget(QtWidgets.QLabel('Date:'))
		layout.addWidget(self.run_date)
		layout.addWidget(QtWidgets.QLabel('Run name:'))
		layout.addWidget(self.run_name)
		layout.addWidget(QtWidgets.QLabel('File number:'))
		layout.addWidget(self.run_file)
		layout.addWidget(self.start_button)

		verticalLayout.addLayout(layout)
		self.file_label = QtWidgets.QLabel('Next File Path:')
		verticalLayout.addWidget(self.file_label)
		self.update_text()
		self.run_date.editingFinished.connect(self.update_text)
		self.run_name.editingFinished.connect(self.update_text)
		self.run_file.valueChanged.connect(self.update_text)

		self.start_button.clicked.connect(self.toggle)
		
		self.setLayout(verticalLayout)
		
		self.incremented.connect(self.update_file)
		
	def isRunning(self):
		return self.running
		
	def increment(self):
		# Emit a signal to trigger updating the UI, so that this can be called from outside the UI thread
		self.cur_file = self.cur_file + 1
		self.incremented.emit(self.cur_file)
		
	def update_file(self, cur_file):
		self.run_file.setValue(cur_file)
			
	def toggle(self):
		if not self.running: # Button pressed while not running, start run
			
			filename, targetPath = 	{ GageMode.TRAD : self.getTarget
			                        , GageMode.SEG  : self.getTargetH5
			                        } [self.mode]()
			
			if not path.exists(targetPath):
				makedirs(targetPath)
			
			if self.analysis_root:
				analysisPath = path.join(self.analysis_root, str(self.run_date.text()))
				
				if not path.exists(analysisPath):
					makedirs(analysisPath)
			
			if path.exists(path.join(targetPath, filename)):
			
				msg = "The target file already exists, overwrite?"
				reply = QtWidgets.QMessageBox.question(self, 'Overwrite confirmation', 
					msg, QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)

				if reply == QtWidgets.QMessageBox.No:
					self.start_button.setChecked(False)
					return

			self.run_date.setEnabled(False)
			self.run_name.setEnabled(False)
			self.run_file.setEnabled(False)
			self.start_button.setText('Running')
			
			self.cur_file = self.run_file.value()
			
			self.running = True

		else:
			self.run_date.setEnabled(True)
			self.run_name.setEnabled(True)
			self.run_file.setEnabled(True)
			
			today = datetime.date.today()
			self.run_date.setText('{:%Y\\%m\\%d}'.format(today))
			
			self.cur_file = 0
			self.run_file.setValue(self.cur_file)
			
			self.start_button.setText('Start')
			
			self.running = False
			
		self.start_button.setChecked(self.running)
		self.status.emit(self.running)
		
	def getRunname(self):
		return self.run_name.text()
		
	def getTarget(self, channel=1):
		date = self.run_date.text()
		runname = self.run_name.text()
		runPath = "{runname:s}_CH{channel:02d}".format(runname=runname, channel=channel)
		targetPath = path.join(self.data_root, str(date), runPath, 'Folder.00001')
		filename = 'AS_CH{channel:02d}-{file:05d}.sig'.format(channel=channel, file=self.cur_file)
		
		return filename, targetPath

	def getTargetH5(self):
		date = self.run_date.text()
		runname = self.run_name.text()
		runPath = "{runname:s}".format(runname=runname)
		targetPath = path.join(self.data_root, str(date), 'data', runPath, 'gagescope')
	
		filename = 'iteration_{file:05d}.h5'.format(file=self.cur_file)
		
		return filename, targetPath

	def update_text(self):
		filename, targetPath = self.getTargetH5()
		self.file_label.setText(f'Next File Name: {path.join(targetPath, filename)}')