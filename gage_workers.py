from __future__ import division,print_function
import csapi
import math
import datetime
import os
from os import path

from qtpy import QtCore
import numpy as np
import h5py

from gage_util import e3decimate,log

class GageCapture(object):
	
	def __init__(self, channel_config, timestamp):
		
		self.channel_config = {cfg.id: cfg for cfg in channel_config} # Reindex as dict
		self.timestamp = timestamp
		
		self.channels = {}
		self.data = {}
		self.channel_rate = {}
		
	def __del__(self):
		log('GageCapture Deleted', 7)
		
	def download(self, gage):
		self.info = gage.GetInfo()
		self.acquisition = gage.GetAcquisition(csapi.Config.ACQUISITION)
		self.trigger = gage.GetTrigger(csapi.Config.ACQUISITION)

		for cid, config in self.channel_config.items():
			self.channels[cid] = gage.GetChannel(channel=cid, config=csapi.Config.ACQUISITION)
			self.channel_rate[cid] = self.acquisition.sample_rate
			self.data[cid] = gage.Download(cid, self.acquisition.segment_size)

	def resample(self):
		for cid, config in self.channel_config.items():
			sample_rate = self.channel_rate[cid]
		
			if config.resample is None or config.resample >= sample_rate:
				continue
			else:
				resample_dec =  int(math.floor(sample_rate / config.resample))
				self.data[cid] = e3decimate(self.data[cid], resample_dec, n=6).astype(np.int16)
				self.channel_rate[cid] = sample_rate / resample_dec

	def prepare_plot(self):
		
		plot_data = {}
		
		for cid, config in self.channel_config.items():
			range_mVpp = self.channels[cid].input_range
			offset_V = self.channels[cid].dc_offset
			resolution = self.acquisition.sample_res
			sample_offset = self.acquisition.sample_offset
			scaled_data= np.double(sample_offset - self.data[cid])/resolution * range_mVpp / 2000.0 + offset_V

			t = np.arange(len(scaled_data), dtype=np.double) / self.channel_rate[cid]
			filt_time, filt_data = config.filter.apply(self.channel_rate[cid], t, scaled_data)
			plot_data[cid] = (filt_time, filt_data)
		
		return plot_data

			
	def save_channel_sig(self, filename, cid):
		
		pack_date, pack_time = self.pack_timestamp(self.timestamp)
		
		gain_range = (20, 10, 4, 2, 1, .4, .2)
		sample_rates = (1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 1e3, 2e3, 5e3, 1e4, 2e4, 5e4, 1e5, 2e5, 5e5,
				1e6, 2e6, 2.5e6, 5e6, 1e7, 1.25e7, 2e7, 2.5e7, 3e7, 4e7, 5e7, 6e7, 6.5e7, 8e7, 
				1e8, 1.2e8, 1.25e8, 1.3e8, 1.5e8, 2e8, 2.5e8, 3e8, 5e8, 1e9, 2e9, 4e9, 5e9, 8e9, 1e10)
		
		channel = self.channels[cid]
		data = self.data[cid]	
		sample_rate = self.channel_rate[cid]
		
		try:
			sample_rate_index = sample_rates.index(sample_rate)
		except ValueError:
			sample_rate_index = 47 #External clock index
		
		try:
			gain_index = gain_range.index(channel.input_range/1000)
		except ValueError:
			raise Exception('Invalid channel input range.')
			
		try:
			trigger_gain_index = gain_range.index(self.trigger.ext_trigger_range/1000)
		except ValueError:
			raise Exception('Invalid trigger input range.')

		header = csapi.SigFileHeader(
			name="Ch {:02d}".format(channel.channel_index),
			sample_rate_index=sample_rate_index,
			operation_mode=2,
			trigger_depth=len(data),
			trigger_slope= 1 if self.trigger.condition else 2, # 1 for rising edge, 2 for falling edge
			trigger_source=127,  #127 for external trigger? to match GS files
			trigger_level=self.trigger.level,
			sample_depth=len(data),
			captured_gain=gain_index,
			captured_coupling=channel.term,
			ending_address=len(data)-1,
			trigger_time=pack_time,
			trigger_date=pack_date,
			trigger_coupling=self.trigger.ext_coupling,
			trigger_gain=trigger_gain_index,
			board_type=self.info.board_type,
			resolution_12_bits=1,
			sample_offset=self.acquisition.sample_offset,
			sample_resolution=self.acquisition.sample_res,
			sample_bits=self.acquisition.sample_bits,
			imped_a=0x10 if channel.impedance == 50 else 0, # 0 for 1 MOhm impedance, 0x10 for 50 Ohm impedance. GS seems to always use imped_a for the current channel?
			imped_b=0x10, # Not sure what setting this corresponds to, set to 0x10 to match typical GS files
			external_tbs=1e9/sample_rate,
			external_clock_rate=sample_rate,
			record_depth=len(data)
		)

		with open(filename, 'wb') as f:
			f.write(header)
			f.write(data.tobytes())
				
	@staticmethod
	def pack_timestamp(ts):
		pack_date = ((ts.year-1980) << 9) | ((ts.month & 0b1111) << 5) |  (ts.day & 0b11111)
		pack_time = (ts.hour << 11) | ((ts.minute & 0b111111) << 5) | ((ts.second>>1) & 0b11111)		
		return (pack_date, pack_time)

	@staticmethod
	def unpack_timestamp(pack_date, pack_time):
		day = pack_date & 0b11111
		month = (pack_date >> 5) & 0b1111
		year = (pack_date >> 9) + 1980
		
		second = (pack_time & 0b11111)*2
		minute = (pack_time >> 5) & 0b111111
		hour = pack_time >> 11
		return datetime.datetime(year, month, day, hour, minute, second)
		

class GageIteration(object):
	
	cur_trigger = 0
	last_trigger = None
	
	def __init__(self, triggers, last_trigger=None):
		self.triggers = triggers
		self.captures = {}
		self.last_trigger = last_trigger

	def __del__(self):
		log('GageIteration Deleted', 7)

	def capture_trigger(self, capture):
		if self.cur_trigger == len(self.triggers):
			raise Exception('Iteration already complete')
		
		next_iteration = None

		detected_trigger = self.check_trigger(self.cur_trigger, capture.timestamp)
		
		if detected_trigger < 0:
			log('Extra trigger at {}! ignoring.'.format(capture.timestamp))
			return (detected_trigger, next_iteration)
		elif detected_trigger == self.cur_trigger:
			self.captures[detected_trigger] = capture
		else:
			log('Missed trigger #{} at {}!'.format(self.cur_trigger, capture.timestamp))
			
			if detected_trigger == 0:
				# First trigger of next iteration
				next_iteration = GageIteration(self.triggers, last_trigger=capture.timestamp)
				next_iteration.captures[0] = capture
				next_iteration.cur_trigger = 1
				#TODO check for bug if nTriggers=1 (missed trigger detection is kind of pointless here...)
			else:
				self.captures[detected_trigger] = capture

		self.cur_trigger = detected_trigger+1
		
		if self.cur_trigger == len(self.triggers):
			# the next trigger is the first of the next iteration. Return a new empty iteration object, initialized with the last_trigger
			next_iteration = GageIteration(self.triggers, last_trigger=self.last_trigger)
			
		return (detected_trigger, next_iteration)

	def check_trigger(self, expected_trigger, timestamp, tolerance=2):

		if not self.last_trigger:
			# First trigger received
			self.last_trigger = timestamp
			return expected_trigger

		_, timeout = self.triggers[expected_trigger]
		
		if timeout == 0:
			self.last_trigger = timestamp
			return expected_trigger			
		
		expected_timestamp = self.last_trigger + datetime.timedelta(seconds=timeout)

		error = (timestamp - expected_timestamp).total_seconds()
		if error < -tolerance:
			# Elapsed time too short, must be an extra trigger.
			# Discard this capture, and continue with the next trigger.
			return -1
		
		elif error > tolerance and expected_trigger > 0:
			# Elapsed time too long, and not the first trigger.
			# (Assume sequence can be interrupted only before
			# first trigger). 
			
			# A trigger must have been missed, in which case the
			# current capture is likely the next trigger in the
			# iteration, or the first trigger of the next iteration.
			#  In either case, continue to check against next step.

			if expected_trigger >= len(self.triggers)-1:
				# If we've advanced beyond the final step in the
				# trigger pattern, assume this is the first file of
				# the next sequence
				return 0
			else:
				# Update last_trigger to expected trigger
				# position, so the current capture can be checked
				# against the next step in the trigger pattern

				# Recurse to check same file against next step
				self.last_trigger = expected_timestamp
				return self.check_trigger(expected_trigger+1, timestamp)
			
		else:
			self.last_trigger = timestamp
			return expected_trigger

	def check_timeout(self, tolerance=2):
		if not self.last_trigger or self.cur_trigger >= len(self.triggers):
			return None

		_, timeout = self.triggers[self.cur_trigger]
		
		if timeout == 0 or self.cur_trigger == 0:
			return None
		
		now = datetime.datetime.now()
		expected_timestamp = self.last_trigger + datetime.timedelta(seconds=timeout)

		while (now - expected_timestamp).total_seconds() > tolerance:
			# If expected trigger is passed
			
			log('Missed trigger #{} at {}!'.format(self.cur_trigger, now))
			self.last_trigger = expected_timestamp
			self.cur_trigger = self.cur_trigger+1
			
			if self.cur_trigger >= len(self.triggers):
				# Missed last trigger, return a new empty iteration
				return GageIteration(self.triggers, last_trigger=self.last_trigger)
			
			_, timeout = self.triggers[self.cur_trigger]
			expected_timestamp = self.last_trigger + datetime.timedelta(seconds=timeout)

		return None

	def get_trigger_timeout(self, tolerance=2):
		if not self.last_trigger or self.cur_trigger >= len(self.triggers):		
			return 0
		
		_, timeout = self.triggers[self.cur_trigger]
		
		if timeout == 0:
			return 0
		
		now = datetime.datetime.now()
		remaining = (self.last_trigger - now) + datetime.timedelta(seconds=timeout+tolerance)
		
		return remaining.total_seconds() * 1000.0

	def save_h5(self, filename):
		
		with h5py.File(filename, 'w') as hf:
			trigger = self.captures[0].trigger
			info = self.captures[0].info
			
			hf.attrs['board_type'] = info.board_type
			hf.attrs['trigger_slope'] = 1 if trigger.condition else 2, # 1 for rising edge, 2 for falling edge
			hf.attrs['trigger_level'] = trigger.level
			hf.attrs['trigger_coupling'] = trigger.ext_coupling
			hf.attrs['trigger_gain'] = trigger.ext_trigger_range
	
			acquisition = self.captures[0].acquisition
	
			for cid, channel in self.captures[0].channels.items():
				hg = hf.create_group('ch{}'.format(cid))
				
				hg.attrs['input_range'] = channel.input_range
				hg.attrs['dc_offset'] =  channel.dc_offset
				hg.attrs['sample_res'] = acquisition.sample_res
				hg.attrs['sample_offset'] = acquisition.sample_offset
				hg.attrs['input_range'] = channel.input_range
				hg.attrs['input_coupling'] = channel.term
				hg.attrs['input_impedance'] = channel.impedance
		
				for idx,values in enumerate(self.triggers):
					prefix, timeout = values
					
					if idx not in self.captures:
						continue
						
					capture = self.captures[idx]
					acquisition = capture.acquisition
		
					field_name = lambda prefix,name: "{}_{}".format(prefix, name) if len(prefix)>0 else name
					
					ts_att = field_name(prefix, 'timestamp')
					hf.attrs[ts_att] = capture.timestamp.isoformat()
	
					segments = capture.channel_config[cid].segments
					dx = 1.0/capture.channel_rate[cid]
	
					for name,start,stop in segments: # start, stop in ms
						imin = int( math.floor(start / 1e3 / dx) )
						imax = int( math.ceil(stop / 1e3 / dx) )
						x0 = imin * dx
						seg_data = capture.data[cid][imin:imax]
						
						dataset_name = field_name(prefix, name)
						dset = hg.create_dataset(dataset_name,  data=seg_data)
						dset.attrs['x0'] = x0
						dset.attrs['dx'] = dx


class GageWorker(QtCore.QObject):
	
	plot_capture = QtCore.Signal(object, int)
	
	def __init__(self):
		super(GageWorker, self).__init__()	
	
	def __del__(self):
		log('GageWorker Deleted', 7)
		
	def started(self):
		pass
	
	def process_capture(self, capture):
		# Resample data
		log('Processing started', 7)

		capture.resample()
		self._process(capture)
		
		log('Processing completed', 7)


class GageTradWorker(GageWorker):
	
	def __init__(self, run_widget):
		super(GageTradWorker, self).__init__()
		
		self.run_widget = run_widget
		
	def _process(self, capture):
		# Save Data
		if self.run_widget.isRunning():
			for cid,config in capture.channel_config.items():
				filename, target_path = self.run_widget.getTarget(channel=cid)
				if not path.exists(target_path):
					os.makedirs(target_path)

				filepath = path.join(target_path, filename)
				capture.save_channel_sig(filepath, cid)
			
				log('Output to {}'.format(filename), 1)
			
			self.run_widget.increment()

		plot_data = capture.prepare_plot()
		self.plot_capture.emit(plot_data, 0)


class GageSegWorker(GageWorker):
	
	def __init__(self, run_widget, triggers):
		super(GageSegWorker, self).__init__()
		
		self.run_widget = run_widget
		self.iteration = GageIteration(triggers)
		
	def started(self):
		self.trigger_timer = QtCore.QTimer()
		self.trigger_timer.timeout.connect(self._check_timeout)
		self.trigger_timer.start(1000)		

	def _process(self, capture):
		(detected_trigger, next_iteration) = self.iteration.capture_trigger(capture)
		if detected_trigger < 0:
			return

		if next_iteration is not None:
			# First trigger of next iteration
			self._save_iteration(self.iteration)
			self.iteration = next_iteration
			
		plot_data = capture.prepare_plot()
		self.plot_capture.emit(plot_data, detected_trigger)
		

	def _save_iteration(self, iteration):
		if not self.run_widget.isRunning():
			return
			
		filename, target_path = self.run_widget.getTargetH5()
		if not path.exists(target_path):
			os.makedirs(target_path)
		filepath = path.join(target_path, filename)
		iteration.save_h5(filepath)
		
		log('Output to {}'.format(filename), 1)
		
		self.run_widget.increment()

	def _check_timeout(self):
		#log('Trigger Timeout ({})'.format(self.iteration.cur_trigger), 5)
		
		#TODO: don't check timeout while there are still captures queued for processing. 
		# Otherwise the timeout might be flagged, even though the correct capture is sitting in the queue
		
		next_iteration = self.iteration.check_timeout()
		if next_iteration is not None:
			# First trigger of next iteration
			self._save_iteration(self.iteration)
			self.iteration = next_iteration

