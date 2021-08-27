from __future__ import division,print_function
from enum import IntEnum
import math
import os
import sys
from configparser import ConfigParser
from datetime import datetime
	
import numpy as np
import pyqtgraph as pg
from scipy import signal

def get_script_path():
	return os.path.dirname(os.path.realpath(sys.argv[0]))

####################

print_level = 10

def log(msg, debug_level=0):
	if debug_level <= print_level:
		timestamp = datetime.now()	
		print('{}: {}'.format(timestamp, msg))

####################

class GageMode(IntEnum):
	TRAD = 1
	SEG = 2
	
class GageState(IntEnum):
	IDLE = 1
	ACQUIRE = 2
	RUN = 3
	
###################
	
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

	return y[tuple(sl)]

class DisplayFilter(object):
		
	def apply(self, sample_rate, t, data):
		return (t, data)

class HeterodyneFilter(DisplayFilter):
	
	def __init__(self, carrier_freq, bw=None, max_length=None):
		self.carrier_freq = carrier_freq
		
		if bw is None:
			self.bw = self.carrier_freq / 2
		else:
			self.bw = bw
			
		self.max_length = max_length

	def apply(self, sample_rate, t, data):
		nDec = int(math.floor(sample_rate / self.bw))
		if self.max_length is not None:
			nDec = max(nDec, int(math.ceil(len(t) / self.max_length)))
			
		carrier_phase = 2*np.pi*self.carrier_freq*t
		iQuad = e3decimate(data * np.cos(carrier_phase), nDec, n=2)
		qQuad = e3decimate(data * np.sin(carrier_phase), nDec, n=2)

		dec_t = t[::nDec]
		
		hetMag = np.sqrt(iQuad**2 + qQuad**2)
		#~ hetPhase = np.arctan2(iQuad, qQuad)
		
		return (dec_t, hetMag)

		
class DecimateFilter(DisplayFilter):
	
	def __init__(self, dec, max_length=None):
		self.dec = dec
	
		self.max_length = max_length
		
	def apply(self, sample_rate, t, data):
		nDec = self.dec
		if self.max_length is not None:
			nDec = max(nDec, int(math.ceil(len(t) / self.max_length)))
		
		filtered = e3decimate(data, nDec, n=2)
		dec_t = t[::nDec]
		return (dec_t, filtered)


class PhotonCounter(DisplayFilter):

	def __init__(self, dec, max_length=None):
		self.dec = dec

		self.max_length = max_length

	def apply(self, sample_rate, t, data):
		nDec = self.dec
		if self.max_length is not None:
			nDec = max(nDec, int(math.ceil(len(t) / self.max_length)))

		filtered = e3decimate(data, nDec, n=2)
		dec_t = t[::nDec]
		return (dec_t, filtered)


class ChannelConfig(object):
	def __init__(self, id, coupling, impedance, range, resample=None, name=None, filter=None, pen=None):
		self.id = id
		self.coupling = coupling
		self.impedance = impedance
		self.range = range
		self.resample = resample
		
		if name is None:
			self.name = 'Channel {}'.format(self.id)
		else:
			self.name = name
		
		if filter is None:
			self.filter = DisplayFilter()
		else:
			self.filter = filter
		
		if pen is None:
			self.pen = [ pg.mkPen('w', width=1) ] #Default pen
		elif len(pen)==1:
			self.pen = [pen]
		else:
			self.pen = pen
			
		self.segments = []
	
	def save_config(self, config):
		sec = 'Channel {}'.format(self.id)
		if not config.has_section(sec):
			config.add_section(sec)
			
		for segment in self.segments:
			(name, start, stop) = segment
			config.set(sec, name, "{:.1f},{:.1f}".format(start,stop))
			
	def load_config(self, config):
		self.segments = []
		
		sec = 'Channel {}'.format(self.id)
		if not config.has_section(sec):
			return
		
		for name, span in config.items(sec):
			start, stop = (float(x) for x in span.split(","))
			self.segments.append((name, start, stop))
			
	def get_pen(self, trigger=0):
		return self.pen[trigger if trigger <= len(self.pen) else -1]

class GageConfig(object):
	
	def __init__(self, channel_config):
		
		self.channel_config = channel_config
		
		self.triggers = []
		
	def save(self, file):

		config = ConfigParser()

		config.add_section('Global')
		
		config.set('Global','mode',self.mode)
		
		if self.mode == GageMode.TRAD:
			config.set('Global','length',self.length_input.value())
		else:
			
			config.add_section('Triggers')
			
			for idx,trigger in enumerate(self.triggers):
				str = trigger.join(',')
				config.set('Triggers','trigger{}'.format(idx),str)
			
			for channel in self.channel_config:
				channel.save_config(config)

		with open(file, 'w') as cf:
			config.write(cf)				