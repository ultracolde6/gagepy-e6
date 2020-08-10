from __future__ import division,print_function
import sys
from shutil import copyfile
import datetime
from os import makedirs, path
import functools
from math import floor

from qtpy import QtCore, QtGui, QtWidgets
		
import numpy as np
import pyqtgraph as pg
from scipy import signal

import csapi
from gage_widgets import RunWidget

pg.setConfigOptions(antialias=True, useWeave=True)

def e3decimate(x, q, n=None, axis=-1, zero_phase=True):
	q = int(q)

	if n is None:
		n = 8
	else:
		n = int(n)
		
	sos = signal.butter(n, 0.8 / q, output='sos')

	sl = [slice(None)] * x.ndim

	if zero_phase:
		y = signal.sosfiltfilt(sos, x, axis=axis)
	else:
		y = signal.sosfilt(sos, x, axis=axis)
	sl[axis] = slice(None, None, q)

	return y[sl]

def init_heterodyne(t):
	global iModel, qModel, carrier_freq
	carrier_phase = 2*np.pi*carrier_freq*t
	iModel = np.cos(carrier_phase)
	qModel = np.sin(carrier_phase)
	
def filter_heterodyne(t, data):
	global iModel, qModel
	dec1 = 400		

	iQuad = e3decimate(data * iModel, dec1, n=6)
	qQuad = e3decimate(data * qModel, dec1, n=6)
	scaled_t = t[::dec1]
	
	hetMag = np.sqrt(iQuad**2 + qQuad**2)
	#~ hetPhase = np.arctan2(iQuad, qQuad)
	
	return (scaled_t, hetMag)
	
def filter_decimate(n, t, data):
	filtered = e3decimate(data, n, n=6)
	scaled_t = t[::n]
	return (scaled_t, filtered)

filter_decimate10 = functools.partial(filter_decimate, 10)
filter_decimate400 = functools.partial(filter_decimate, 400)

class ChannelConfig:
	def __init__(self, id, coupling, impedance, range, resample=None):
		self.id = id
		self.coupling = coupling
		self.impedance = impedance
		self.range = range
		self.resample = resample

####################		
## configuration
####################		

dataRoot = 'E:\\Data\\'
analysisRoot = 'E:\\Analysis\\'

csapi.Initialize()

sample_clk = 80e6
carrier_freq = 10e6

trigger_config = (csapi.TriggerSource.EXT, csapi.Coupling.DC, csapi.Impedance.Z_1M, csapi.Gain.G_10Vpp)

channel_config = (
	ChannelConfig(1, csapi.Coupling.DC, csapi.Impedance.Z_1M, csapi.Gain.G_4Vpp),
	ChannelConfig(2, csapi.Coupling.DC, csapi.Impedance.Z_1M, csapi.Gain.G_2Vpp, resample=2e6),
#	ChannelConfig(3, csapi.Coupling.DC, csapi.Impedance.Z_1M, csapi.Gain.G_2Vpp, resample=2e6),
)

plot_config = {
	1: ('Heterodyne', init_heterodyne, filter_heterodyne, pg.mkPen('y', width=1)),
	2: ('VCO', None, filter_decimate10, pg.mkPen('g', width=1)),
	3: ('ODT', None, filter_decimate10, pg.mkPen('r', width=1)),
}

####################		

#TODO add out of range warnings!

class GageWindow(QtWidgets.QMainWindow):
	
	gage = None
	
	acquired = QtCore.Signal(datetime.datetime)
	
	def __init__(self, parent=None):
		super(GageWindow, self).__init__(parent)
		
		self._acquiring = False
		self.sample_length = 12.0
		
		self.setupUi()

		self.gage = csapi.System(reset=False)
		self.info = self.gage.GetInfo()
		
		self.gage.RegisterCallback(csapi.AcquisitionEvent.END_BUSY, self.onAcquired)
		self.acquired.connect(self.processAcquisition)
		

	def closeEvent(self, event):
		self._acquiring = False		
		self.gage.Abort()
		self.gage.Close()
		self.gage = None

	def setConfig(self):		
		self.gage.SetAcquisition(
			sample_rate = int(sample_clk),
			extclk = int(sample_clk),
			mode = csapi.Mode.QUAD,
			segment_count = 1,
			depth = self.sample_depth,
			trigger_timeout = -1, # Set to CS_TIMEOUT_DISABLE=-1
			segment_size = self.sample_depth
		)
		
		for channel in channel_config:
			self.gage.SetChannel(channel.id, 
				term = channel.coupling,
				impedance = channel.impedance,
				input_range = channel.range, # in [mV]
			)
			
		(source, coupling, imped, range) = trigger_config
		self.gage.SetTrigger(
			condition = 1, #Rising slope
			ext_trigger_range = range, # Vpp range in [mV]
			ext_impedance = imped, # in Ohms
			ext_coupling = coupling, # DC coupling
			source = source,
			level = 30 # Percentage of range/2
		)

		self.gage.Commit()

		# initialize channel filters
		t = np.arange(self.sample_depth) / sample_clk
		for channel in channel_config:
			if plot_config.has_key(channel.id):
				(name, init_func, filter_func, pen) = plot_config[channel.id]	

				if init_func is not None:
					if channel.resample is None:
						decimation_factor = 1
					else:
						decimation_factor =  floor(sample_clk / channel.resample)

					init_func(t[::decimation_factor])
		
	def setupUi(self):
		self.setWindowTitle("Gage Acquire")
		self.centralWidget = QtWidgets.QWidget()
		self.setCentralWidget(self.centralWidget)
		self.resize(1024,768)
		layout = QtWidgets.QVBoxLayout()		
				
		acquisition_layout = QtWidgets.QHBoxLayout()

		self.start_button = QtWidgets.QPushButton('Start Acquisition')
		self.start_button.setCheckable(True)
		self.start_button.clicked.connect(self.toggleStart)
		
		self.length_input = QtWidgets.QDoubleSpinBox()
		self.length_input.setDecimals(1)
		self.length_input.setRange(1,200)
		self.length_input.setDecimals(1)
		self.length_input.setSuffix(' ms')
		self.length_input.setValue(self.sample_length)		
		self.length_input.setFixedWidth(120)
		
		acquisition_layout.addWidget(self.start_button)
		label = QtWidgets.QLabel('Length: ')
		label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
		acquisition_layout.addWidget(label)
		acquisition_layout.addWidget(self.length_input)
		#acquisition_layout.addWidget(QLabel('ms'))
			
		layout.addLayout(acquisition_layout)
		
		self.channel_plots = {}
		self.channel_lines = {}
		for channel in channel_config:
			plot = pg.PlotWidget(self)
			self.channel_plots[channel.id] = plot
							
			plot_item = plot.getPlotItem()
			plot_item.setLabel('bottom', text='Time', units='s')
			plot_item.setLabel('left', text='Signal', units='V')
			plot_item.addLegend(size=(100, 40), offset=(-20, 20))
			
			name = 'Channel {}'.format(channel.id)
			pen =  pg.mkPen('w', width=1) #Default pen
			if plot_config.has_key(channel.id):
				(name, init_func, filter_func, pen) = plot_config[channel.id]
			
				data_item = pg.PlotDataItem(pen=pen,name=name)
				plot_item.addItem(data_item)
				self.channel_lines[channel.id] = data_item			
			
			layout.addWidget(plot)
			
		self.run_widget = RunWidget(dataRoot, analysis_root=analysisRoot)
		self.run_widget.status.connect(self.runStatus)
		self.run_widget.setEnabled(False)
		
		layout.addWidget(self.run_widget)
		self.centralWidget.setLayout(layout)       

	def toggleStart(self):
		if self.start_button.isChecked():
			self.start_button.setText('Starting...')
			
			self.sample_length = self.length_input.value()
			self.sample_depth = int( sample_clk * self.sample_length / 1e3)
			
			print('Starting acquisition for {:.1f} ms ({:d} samples)'.format(self.sample_length, self.sample_depth))
			self.setConfig()
			
			for channel in channel_config:
				self.channel_plots[channel.id].setXRange(0, self.sample_length*1e-3)
			
			self._acquiring = True
			self.gage.Start()
			self.start_button.setText('Acquiring')
			self.length_input.setEnabled(False)
			self.run_widget.setEnabled(True)
		else:
			self.start_button.setText('Stopping...')			
			self._acquiring = False
			self.gage.Abort()
			self.start_button.setText('Start Acquisition')
			self.length_input.setEnabled(True)
			self.run_widget.setEnabled(False)
			
			print('Acquisition stopped')
		
	def runStatus(self, running):
		runname = self.run_widget.getRunname()
		if running:
			print('Run ''{}'' started'.format(runname))
			self.start_button.setEnabled(False)
		else:
			print('Run ''{}'' stopped'.format(runname))
			self.start_button.setEnabled(True)
		
	def onAcquired(self, cbInfo):
		timestamp = datetime.datetime.now()
		self.acquired.emit(timestamp)
	
	def processAcquisition(self, timestamp):
		if not self._acquiring:
			return
		
		acquisition = self.gage.GetAcquisition(csapi.Config.ACQUISITION)
		trigger = self.gage.GetTrigger(csapi.Config.ACQUISITION)

		channels = {}
		data = {}
		for channel in channel_config:
			channels[channel.id] = self.gage.GetChannel(channel=channel.id, config=csapi.Config.ACQUISITION)
			data[channel.id] = self.gage.Download(channel.id, acquisition.depth)

		# print('Acquired!')		
		self.gage.Start()
		
		# Resample data
		resampled = {}
		for channel in channel_config:
			if channel.resample is None:
				resampled[channel.id] = 1
				continue
						
			sample_rate = acquisition.sample_rate
			decimation_factor =  int(floor(sample_rate / channel.resample))
			
			filtered = e3decimate(data[channel.id], decimation_factor, n=6).astype(np.int16)

			resampled[channel.id] = decimation_factor
			data[channel.id] = filtered
			
			
		# Save Data
		if self.run_widget.isRunning():
			for channel in channel_config:
				filename, targetPath = self.run_widget.getTarget(channel=channel.id)
				if not path.exists(targetPath):
					makedirs(targetPath)

				file = path.join(targetPath, filename)
				self.saveChannel(file, acquisition, trigger, channels[channel.id], data[channel.id], timestamp, resampled[channel.id] )
				
				print('Output to {}'.format(filename))
				
			self.run_widget.increment()

		# Scale, filter, and plot data
		t = np.arange(self.sample_depth, dtype=np.double) / acquisition.sample_rate
		for channel in channel_config:
			range_mVpp = channels[channel.id].input_range
			offset_V = channels[channel.id].dc_offset
			resolution = acquisition.sample_res
			sample_offset = acquisition.sample_offset
			scaled_data= (sample_offset - data[channel.id])/resolution * range_mVpp / 2000.0 + offset_V

			filter_func = None
			if plot_config.has_key(channel.id):
				(name, init_func, filter_func, pen) = plot_config[channel.id]

			resampled_t = t[::resampled[channel.id]]				
			if filter_func is not None:
				plot_time, plot_data = filter_func(resampled_t, scaled_data)
			else:
				plot_time, plot_data = (resampled_t, scaled_data)
			
			self.channel_lines[channel.id].setData(plot_time, plot_data)

	def saveChannel(self, filename, acquisition, trigger, channel, data, ts, resampled=1):
		
		pack_date =((ts.year-1980) << 9) | ((ts.month & 0b1111) << 5) |  (ts.day & 0b11111)
		pack_time = (ts.hour << 11) | ((ts.minute & 0b111111) << 5) | ((ts.second>>1) & 0b11111)
				
		# Unpack date and time example
		#~ day = pack_date & 0b11111
		#~ month = (pack_date >> 5) & 0b1111
		#~ year = (pack_date >> 9) + 1980
		
		#~ second = (pack_time & 0b11111)*2
		#~ minute = (pack_time >> 5) & 0b111111
		#~ hour = pack_time >> 11
		
		gain_range = (20, 10, 4, 2, 1, .4, .2)
		sample_rates = (1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 1e3, 2e3, 5e3, 1e4, 2e4, 5e4, 1e5, 2e5, 5e5,
				1e6, 2e6, 2.5e6, 5e6, 1e7, 1.25e7, 2e7, 2.5e7, 3e7, 4e7, 5e7, 6e7, 6.5e7, 8e7, 
				1e8, 1.2e8, 1.25e8, 1.3e8, 1.5e8, 2e8, 2.5e8, 3e8, 5e8, 1e9, 2e9, 4e9, 5e9, 8e9, 1e10)
		
		sample_rate = acquisition.sample_rate / resampled
		ext_clk_rate = acquisition.extclk / resampled
		
		try:
			sample_rate_index = sample_rates.index(sample_rate)
		except ValueError:
			sample_rate_index = 47 #External clock index
		
		try:
			gain_index = gain_range.index(channel.input_range/1000)
		except ValueError:
			raise Exception('Invalid channel input range.')
			
		try:
			trigger_gain_index = gain_range.index(trigger.ext_trigger_range/1000)
		except ValueError:
			raise Exception('Invalid trigger input range.')
			
		acq_depth = floor(acquisition.depth / resampled)
		if len(data) != acq_depth:
			warning('Length of data vector to save does not match reported acquisition depth')

		header = csapi.SigFileHeader(
			name="Ch {:02d}".format(channel.channel_index),
			sample_rate_index=sample_rate_index,
			operation_mode=2,
			trigger_depth=len(data),
			trigger_slope= 1 if trigger.condition else 2, # 1 for rising edge, 2 for falling edge
			trigger_source=127,  #127 for external trigger? to match GS files
			trigger_level=trigger.level,
			sample_depth=len(data),
			captured_gain=gain_index,
			captured_coupling=channel.term,
			ending_address=len(data)-1,
			trigger_time=pack_time,
			trigger_date=pack_date,
			trigger_coupling=trigger.ext_coupling,
			trigger_gain=trigger_gain_index,
			board_type=self.info.board_type,
			resolution_12_bits=1,
			sample_offset=acquisition.sample_offset,
			sample_resolution=acquisition.sample_res,
			sample_bits=acquisition.sample_bits,
			imped_a=0x10 if channel.impedance == 50 else 0, # 0 for 1 MOhm impedance, 0x10 for 50 Ohm impedance. GS seems to always use imped_a for the current channel?
			imped_b=0x10, # Not sure what setting this corresponds to, set to 0x10 to match typical GS files
			external_tbs=1e9/ext_clk_rate,
			external_clock_rate=ext_clk_rate,
			record_depth=len(data)
		)

		with open(filename, 'wb') as f:
			f.write(header)
			f.write(data.tobytes())


## Start Qt event loop unless running in interactive mode.
def main():

	try:
		import ctypes
		myappid = u'ultracold.gage_acquire' # arbitrary string
		ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)    
	except:
		pass
	
	app = QtWidgets.QApplication(sys.argv)    
	app.setWindowIcon(QtGui.QIcon('favicon.ico'))
	ex = GageWindow()
	ex.show()
	sys.exit(app.exec_())

if __name__ == '__main__':
	main()
