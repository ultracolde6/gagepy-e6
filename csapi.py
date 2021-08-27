#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Container and wrapper of all C routines of CsSsm.dll of GaGe CompuScope
into Python.
See www.gage-applied.com/support/sdks/CsAPI.chm as API Reference
for documentation of all options and the definitions of constants.

by Markus Haehnel

Obtained from https://sourceforge.net/projects/hzdr/
Modified by Jonathan Kohler (jkohler@berkeley.edu)
"""  

#  Copyright 2014  <>
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

from __future__ import division,print_function
import ctypes as ct
from enum import Enum,IntEnum
from sys import platform as sys_plat

debug = False           # output success error codes

class CompuScopeError(Exception):
	"""
	Name an exception for clear output.
	"""
	pass



##############
# Structures #
##############


class BaseStructure(ct.Structure):

	def __init__(self, **kwargs):
		"""
		ctypes.Structure with integrated default values.

		:param kwargs: values different to defaults
		:type kwargs: dict
		"""

		values = type(self)._defaults_.copy()
		for (key, val) in kwargs.items():
			values[key] = val

		super(BaseStructure, self).__init__(**values)


class SystemInfo(BaseStructure):
	"""
	Structure contains the static information describing the CompuScope.
	"""
	_fields_ = [("size", ct.c_uint32),
			("max_memory", ct.c_int64),
			("sample_bits", ct.c_uint32),
			("sample_resolution", ct.c_int32),
			("sample_size", ct.c_uint32),
			("sample_offset", ct.c_int32),
			("board_type", ct.c_uint32),
			("board_name", ct.c_char * 32),
			("addon_options", ct.c_uint32),
			("baseboard_options", ct.c_uint32),
			("trigger_machine_count", ct.c_uint32),
			("channel_count", ct.c_uint32),
			("board_count", ct.c_uint32),
		]
	_defaults_ = { "size" : 88 }


class AcquisitionConfig(BaseStructure):
	"""
	This structure is used to set or query configuration settings of the
	CompuScope system.
	"""
	_fields_ = [("size", ct.c_uint32),
			("sample_rate", ct.c_int64),
			("extclk", ct.c_uint32),
			("extclk_sample_skip", ct.c_uint32),
			("mode", ct.c_uint32),
			("sample_bits", ct.c_uint32),
			("sample_res", ct.c_int32),
			("sample_size", ct.c_uint32),
			("segment_count", ct.c_uint32),
			("depth", ct.c_int64),
			("segment_size", ct.c_int64),
			("trigger_timeout", ct.c_int64),
			("trig_engines_en", ct.c_uint32),
			("trigger_delay", ct.c_int64),
			("trigger_holdoff", ct.c_int64),
			("sample_offset", ct.c_int32),
			("timestamp_config", ct.c_uint32),
		]
	_defaults_ = {
			"size" : 104,
			"extclk" : 0, # disable external clocking
			"trigger_timeout" : -1, # [sample clock cycles] infinite=-1
			"trigger_delay" : 0,
			"trigger_holdoff" : 0,
			"timestamp_config" : 0, # sample clock based, reset on capture start
		}


class ChannelConfig(BaseStructure):
	"""
	This structure is used to set or query channel-specific
	configuration settings. Each channel within the system has its own
	configuration structure.
	"""
	_fields_ = [("size", ct.c_uint32),
			("channel_index", ct.c_uint32),
			("term", ct.c_uint32),
			("input_range", ct.c_uint32),
			("impedance", ct.c_uint32),
			("filter", ct.c_uint32),
			("dc_offset", ct.c_int32),
			("calib", ct.c_int32),
		]
	_defaults_ = {
			"size": 32,
			"term": 1, # DC coupling
			"impedance": 50, # 1 MOhm
			"filter": 0, # no filter
			"dc_offset": 0, # [mV]
			"calib": 0,
		}


class TriggerConfig(BaseStructure):
	"""
	This structure is used to set or query parameters of the trigger
	engine. Each trigger engine is described separately.  
	"""
	_fields_ = [("size", ct.c_uint32),
			("trigger_index", ct.c_uint32),
			("condition", ct.c_uint32),
			("level", ct.c_int32),
			("source", ct.c_int32),
			("ext_coupling", ct.c_uint32),
			("ext_trigger_range", ct.c_uint32),
			("ext_impedance", ct.c_uint32),
			("value1", ct.c_int32),
			("value2", ct.c_int32),
			("filter", ct.c_uint32),
			("relation", ct.c_uint32),
		]
	_defaults_ = {
			"size": 48,
			"trigger_index": 1, # first engine
			"condition": 0, # falling slope
			"level": 30, # 0% of input range
			"source": 0, # by timeout or manually
			"ext_trigger_range": 5000,# [mV]
			"ext_impedance": 50,     # [Ohm]
			"ext_coupling": 1, # DC coupling
		}


class In_Params_TransferData(BaseStructure):
	"""
	Structure used in CsTransfer() to specify data to be transferred.
	May be used to transfer digitized data or time-stamp data. 
	"""
	_fields_ = [("channel", ct.c_uint16),
			("mode", ct.c_uint32),
			("segment", ct.c_uint32), #The segment of interest.
			("start_address", ct.c_int64), #Start address for transfer relative to the trigger address
			("length", ct.c_int64), #Size of the requested data transfer (in samples)
			("data_buffer", ct.c_void_p),
			("hNotifyEvent", ct.POINTER(ct.c_void_p)),
		]
	_defaults_ = {
			"mode": 4, # transfer all data
			"segment": 1, # first segment
			"start_address": 0, # first sample after trigger
		}


class Out_Params_TransferData(ct.Structure):
	"""
	Structure used in CsTransfer() to hold output parameters.
	"""
	_fields_ = [("actual_start", ct.c_int64), #Address relative to the trigger address of the first sample in the buffer
			("actual_length", ct.c_int64), #Length of valid data in the buffer
			("low_part", ct.c_int32),
			("high_part", ct.c_int32),
		]


class In_Params_TransferData_Ex(BaseStructure):
	"""
	Structure used in CsTransferEx() to specify data to be transferred. 
	"""
	_fields_ = [("channel", ct.c_uint16),
				("mode", ct.c_uint32),
				("start_segment", ct.c_uint32),
				("segment_count", ct.c_uint32),
				("start_address", ct.c_int64),
				("length", ct.c_int64),
				("data_buffer", ct.c_void_p),
				("buffer_length", ct.c_int64),
				("hNotifyEvent", ct.POINTER(ct.c_void_p)),
			]
	_defaults_ = {
				"mode": 10, # transfer data as 32-bit samples
				"start_segment": 0, # first segment after trigger
				"start_address": 0, # first sample after trigger
			}


class Out_Params_TransferData_Ex(ct.Structure):
	"""
	Structure used in CsTransferEx() to return format of the transferred
	data.
	"""
	_fields_ = [("DataFormat0", ct.c_uint32),
				("Dataformat1", ct.c_uint32),
			]


class DiskFileHeader(ct.Structure):
	"""
	Structure used dealing with SIG file headers.
	"""
	_fields_ = [("cData", ct.c_char * 512),
				]


class SigFileHeader(BaseStructure):
	"""
	Structure used dealing with SIG file headers.
	"""
	_pack_ = 1
	_fields_ = [
		("file_version", ct.c_char * 14),
		("crlf1", ct.c_char * 2),
		("name", ct.c_char * 9),
		("crlf2", ct.c_char * 2),
		("comment", ct.c_char * 256),
		("crlf3", ct.c_char * 2),
		("control_z", ct.c_char * 2),
		("sample_rate_index", ct.c_int16),
		("operation_mode", ct.c_int16),
		("trigger_depth", ct.c_int32),
		("trigger_slope", ct.c_int16),
		("trigger_source", ct.c_int16),
		("trigger_level", ct.c_int16),
		("sample_depth", ct.c_int32),
		("captured_gain", ct.c_int16),
		("captured_coupling", ct.c_int16),
		("current_mem_ptr", ct.c_int32),
		("starting_address", ct.c_int32),
		("trigger_address", ct.c_int32),
		("ending_address", ct.c_int32),    
		("trigger_time", ct.c_uint16),
		("trigger_date", ct.c_uint16),
		("trigger_coupling", ct.c_int16),
		("trigger_gain", ct.c_int16),
		("probe", ct.c_int16),    
		("inverted_data", ct.c_int16),
		("board_type", ct.c_uint16),
		("resolution_12_bits", ct.c_int16),
		("multiple_record", ct.c_int16),
		("trigger_probe", ct.c_int16),    
		("sample_offset", ct.c_int16),    
		("sample_resolution", ct.c_int16),
		("sample_bits", ct.c_uint16),
		("extended_trigger_time", ct.c_uint32),
		("imped_a", ct.c_int16),
		("imped_b", ct.c_int16),    
		("external_tbs", ct.c_float),
		("external_clock_rate", ct.c_float),    
		("file_options", ct.c_int32),
		("version", ct.c_uint16),
		("eeprom_options", ct.c_uint32),
		("trigger_hardware", ct.c_uint32),    
		("record_depth", ct.c_uint32),
		("padding", ct.c_ubyte*127),    
	]
	_defaults_ = { 
		"file_version": 'GS V.3.00',
		"crlf1": '\r\n',
		"crlf2": '\r\n',
		"comment": 'Saved from CompuScope API for Python',
		"crlf3": '\r\n',
		"control_z":'\x1a\0'
	}


class TimeStamp(ct.Structure):
	"""
	Structure used in to store the timestamp information.
	"""
	_fields_ = [("hour", ct.c_uint16),
			("minute", ct.c_uint16),
			("second", ct.c_uint16),
			("point1_second", ct.c_uint16),
		]


class SigStruct(BaseStructure):
	"""
	Structure used in to create SIG file headers, or to convert between
	SIG file headers. 
	"""
	_fields_ = [("size", ct.c_uint32),
			("sample_rate", ct.c_int64),
			("record_start", ct.c_int64),
			("record_length", ct.c_int64),
			("record_count", ct.c_uint32),
			("sample_bits", ct.c_uint32),
			("sample_size", ct.c_uint32),
			("sample_offset", ct.c_int32),
			("sample_res", ct.c_int32),
			("channel", ct.c_uint32),
			("input_range", ct.c_uint32),
			("dc_offset", ct.c_int32),
			("timestamp", TimeStamp),
		]
	_defaults_ = {"size": 72}


class CallbackData(BaseStructure):
	"""
	Structure used in to create SIG file headers, or to convert between
	SIG file headers. 
	"""
	_fields_ = [("size", ct.c_uint32),
			("hSystem", ct.c_ulong),
			("channel_index", ct.c_uint32),
			("token", ct.c_int32),
		]
	_defaults_ = {"size": 16}

############
# Constant enums #
############

class Coupling(IntEnum):
	DC = 1 # DC coupling.
	AC = 2 # AC coupling. 

class Impedance(IntEnum):
	Z_1M = 1000000 # 1 MOhm impedance
	Z_50 = 50 # 50 Ohm impedance

class Gain(IntEnum):
	G_100Vpp = 100000 # 100 Vpp input range 
	G_40Vpp = 40000 # 40 Vpp input range 
	G_20Vpp = 20000 # 20 Vpp input range 
	G_10Vpp = 10000 # 10 Vpp input range 
	G_8Vpp = 8000 # 8 Vpp input range 
	G_4Vpp = 4000 # 4 Vpp input range 
	G_2Vpp = 2000 # 2 Vpp input range 
	G_1Vpp = 1000 # 1 Vpp input range 
	G_800mVpp = 800 # 800 mVpp input range 
	G_400mVpp = 400 # 400 mVpp input range 
	G_200mVpp = 200 # 200 mVpp input range 
	G_100mVpp = 100 # 100 mVpp input range  

class AcquisitionEvent(IntEnum):
	TRIGGERED = 0 # Trigger event.
	END_BUSY = 1 # End of acquisition event. 
	END_TXFER = 2 # End of transfer event. 

class TriggerSource(IntEnum):
	DISABLE = 0 # Disable trigger engines. Trigger manually or by timeout. 
	CHAN_1 = 1 # Use channel index to specify the channel as trigger source. 
	CHAN_2 = 2 # Use channel index to specify the channel as trigger source. 
	CHAN_3 = 3 # Use channel index to specify the channel as trigger source. 
	CHAN_4 = 4 # Use channel index to specify the channel as trigger source. 
	EXT = -1 # Use external trigger input as trigger source.  
	
class Action(IntEnum):
	COMMIT = 1 # Transfers configuration setting values from the drivers to the CompuScope hardware. 
	START = 2 # Starts acquisition. 
	FORCE = 3 # Emulates a trigger event.
	ABORT = 4 # Aborts an acquisition or a transfer. 
	CALIB = 5 # Invokes CompuScope on-board auto-calibration sequence.
	RESET = 6 # Reset the system. 
	COMMIT_COERCE = 7 # Transfers configuration setting values from the drivers to the CompuScope hardware. 
	ACTION_TIMESTAMP_RESET = 8 # Resets the time-stamp counter. 

class Index(IntEnum):
	BOARD_INFO  = 1 #  Version information about the CompuScope system. 
	SYSTEM  = 3 #  Static information about the CompuScope system. 
	CHANNEL  = 4 #  Dynamic configuration of channels. 
	TRIGGER  = 5 #  Dynamic configuration of the trigger engines. 
	ACQUISITION =  6 #  Dynamic configuration of the acquisition. 
	FIR_CONFIG  = 8 #  Configuration parameters for FIR filter firmware. 
	EXTENDED_BOARD_OPTIONS  = 9 #  Query information about 2nd and 3rd base-board FPGA images. 
	TIMESTAMP_TICKFREQUENCY  = 10 #  Query the timestamp tick frequency. 
	CHANNEL_ARRAY  = 11 #  Dynamic configuration of the array of channels. 
	TRIGGER_ARRAY  = 12 #  Dynamic configuration of the array of triggers. 
	SMT_ENVELOPE_CONFIG =  13 #  Configuration parameters for Storage Media Testing firmware. 
	SMT_HISTOGRAM_CONFIG  = 14 #  Configuration parameters for Storage Media Testing firmware. 
	FFT_CONFIG  = 15 #  Configuration parameters for FFT filter firmware. 
	FFTWINDOW_CONFIG = 16 #  Window coefficients for FFT eXpert firmware. 
	MULREC_AVG_COUNT = 17 #  Configuration parameters for eXpert MulRec Averaging firmware. 
	TRIG_OUT_CFG = 18 #  Configuration of the Trigger Out synchronisation.      

class Config(IntEnum):
	CURRENT = 1 # Retrieve data from the configuration settings from the driver. 
	ACQUISITION = 2 # Retrieve hardware configuration settings from the most recent acquisition. 
	ACQUIRED = 3 #  Retrieve the configuration settings that relates to the acquisition buffer. 
	
class Status(IntEnum):
	READY = 0 # Ready for acquisition or data transfer. 
	WAIT_TRIGGER = 1 # Waiting for trigger event. 
	TRIGGERED = 2 # CompuScope system has been triggered but is still busy acquiring. 
	BUSY_TX = 3 # Data transfer is in progress. 
	BUSY_CALIB = 4 # CompuScope on-board auto-calibration sequence is in progress.  

class Mode(IntEnum):
	SINGLE = 0x1 # Single channel acquisition. 
	DUAL = 0x2 # Dual channel acquisition. 
	QUAD = 0x4 # Four channel acquisition. 
	OCT = 0x8 # Eight channel acquisition. 
	POWER_ON = 0x80 # Disable power saving mode. 
	PRETRIG_MULREC = 0x200 # Use alternate firmware for Pre-trigger Multiple Record Mode. 
	REFERENCE_CLK = 0x400 # Use 10 MHz reference clock. 
	CS3200_CLK_INVERT = 0x800 # Use falling edge of the clock on CS3200 and CS3200C. 
	SW_AVERAGING = 0x1000 #  Use software averaging acquisition mode.    
	#USER1 = 0x40000000 # Use alternative firmware image 1. 
	#USER2 = 0x80000000 # Use alternative firmware image 2. 

class Capabilities(Enum):
	SAMPLE_RATES = 0x10000 # Query for available sample rates. 
	INPUT_RANGES = 0x20000 # Query for available input ranges. 
	IMPEDANCES = 0x30000 # Query for available impedances. 
	COUPLINGS = 0x40000 # Query for available couplings. 
	ACQ_MODES = 0x50000 # Query for available capture modes. 
	TERMINATIONS = 0x60000 # Query for available channel terminations. 
	FLEXIBLE_TRIGGER = 0x70000 # Query for availability of flexible triggering (triggering from any of cards in system). 
	BOARD_TRIGGER_ENGINES = 0x80000 # Query for number of trigger engines per board. 
	TRIGGER_SOURCES = 0x90000 # Query for trigger sources available. 
	FILTERS = 0xA0000 # Query for available built-in filters. 
	MAX_SEGMENT_PADDING = 0xB0000 # Query for Max Padding for segment or depth. 
	DC_OFFSET_ADJUST = 0xC0000 # Query for DC Offset adjustment capability. 
	CLK_IN = 0xD0000 # Query for external synchronisation clock inputs. 
	TRIG_ENGINES_PER_CHAN = 0x200000 # Query for number of trigger engines per channel. 
	MULREC = 0x400000 # Query for multiple record capability. 
	TRIGGER_RES = 0x410000 # Query for trigger resolution. 
	MIN_EXT_RATE = 0x420000 # Query for minimum external clock rate. 
	SKIP_COUNT = 0x430000 # Query for external clock skip count. 
	MAX_EXT_RATE = 0x440000 # Query for maximum external clock rate. 
	TRANSFER_EX = 0x450000 # Query for CsTransferEx() support.  

############
# Routines #
############

class DllContainer(object):

	def __init__(self, dll, dlltype=None):
		"""
		Over class of ctypes that the Dynamic Linked Library is
		loaded on first call instead at module initialization yet.
		So it's possible to import the csapi module on system without
		the DLL installed but not to execute.

		:param dll: name of DLL to load
		:type dll: str
		:param dlltype: class to load DLL
		:type dlltype: ctypes class
		"""

		if dlltype is None:
			dlltype = ct.WinDLL if hasattr(ct, "WinDLL") else ct.CDLL
			# dlltype = ct.CDLL
	

		self.dll = None
		self.name = dll
		self.type = dlltype


	def __getattr__(self, name):
		"""
		Forward call to DLL. Load DLL on first call.
		"""

		if self.dll is None:
			self.load_dll()

		return self.dll.__getattribute__(name)


	def load_dll(self):
		"""
		Load DLL.
		"""

		self.dll = self.type(self.name)


		# Initialization

		self.dll.CsInitialize.argtypes = []
		self.dll.CsInitialize.restype = ct.c_int32

		self.dll.CsGetSystem.argtypes = [ct.POINTER(ct.c_ulong), ct.c_uint32,
											ct.c_uint32, ct.c_uint32, ct.c_int16]
		self.dll.CsGetSystem.restype = ct.c_int32


		# Configuration
		self.dll.CsGet.argtypes = [ct.c_ulong, ct.c_int32, ct.c_int32, ct.c_void_p]
		self.dll.CsGet.restype = ct.c_int32

		self.dll.CsSet.argtypes = [ct.c_ulong, ct.c_int32, ct.c_void_p]
		self.dll.CsSet.restype = ct.c_int32

		self.dll.CsDo.argtypes = [ct.c_ulong, ct.c_int16]
		self.dll.CsDo.restype = ct.c_int32

		self.dll.CsExpertCall.argtypes = [ct.c_ulong, ct.c_void_p]
		self.dll.CsExpertCall.restype = ct.c_int32


		# Events

		self.dll.CsGetEventHandle.argtypes = [ct.c_ulong, ct.c_uint32, ct.POINTER(ct.c_void_p)]
		self.dll.CsGetEventHandle.restype = ct.c_int32

		self.dll.CsRegisterCallbackFnc.argtypes = [ct.c_ulong, ct.c_uint32, ct.c_void_p]
		self.dll.CsRegisterCallbackFnc.restype = ct.c_int32


		# After acquisition

		self.dll.CsFreeSystem.argtypes = [ct.c_ulong]
		self.dll.CsFreeSystem.restype = ct.c_int32

		self.dll.CsTransfer.argtypes = [ct.c_ulong, ct.POINTER(In_Params_TransferData),
									ct.POINTER(Out_Params_TransferData)]
		self.dll.CsTransfer.restype = ct.c_int32

		self.dll.CsTransferEx.argtypes = [ct.c_ulong, ct.POINTER(In_Params_TransferData_Ex),
									ct.POINTER(Out_Params_TransferData_Ex)]
		self.dll.CsTransferEx.restype = ct.c_int32

		self.dll.CsTransferAS.argtypes = [ct.c_ulong, ct.POINTER(In_Params_TransferData),
									ct.POINTER(Out_Params_TransferData), ct.POINTER(ct.c_int32)]
		self.dll.CsTransferAS.restype = ct.c_int32

		self.dll.CsGetTransferASResult.argtypes = [ct.c_ulong, ct.c_int32, ct.POINTER(ct.c_int64)]
		self.dll.CsGetTransferASResult.restype = ct.c_int32

		self.dll.CsRetrieveChannelFromRawBuffer.argtypes = [ct.c_void_p, ct.c_int64, ct.c_uint32,
						ct.c_uint16, ct.c_int64, ct.c_int64, ct.c_void_p, ct.POINTER(ct.c_int64),
						ct.POINTER(ct.c_int64), ct.POINTER(ct.c_int64)]
		self.dll.CsRetrieveChannelFromRawBuffer.restype = ct.c_int32


		# Informations

		self.dll.CsGetSystemInfo.argtypes = [ct.c_ulong, ct.POINTER(SystemInfo)]
		self.dll.CsGetSystemInfo.restype = ct.c_int32
		self.dll.CsGetSystemCaps.argtypes = [ct.c_ulong, ct.c_uint32,
														ct.c_void_p, ct.POINTER(ct.c_uint32)]
		self.dll.CsGetSystemCaps.restype = ct.c_int32

		self.dll.CsGetStatus.argtypes = [ct.c_ulong]
		self.dll.CsGetStatus.restype = ct.c_int32


		# Miscellaneous

		self.dll.CsGetErrorString.argtypes = [ct.c_ulong, ct.c_char_p, ct.c_int]
		self.dll.CsGetErrorString.restype = ct.c_int32

		self.dll.CsConvertToSigHeader.argtypes = [ct.POINTER(DiskFileHeader), ct.POINTER(SigStruct),
												ct.c_void_p, ct.c_void_p]
		self.dll.CsConvertToSigHeader.restype = ct.c_int32

		self.dll.CsConvertFromSigHeader.argtypes = [ct.POINTER(DiskFileHeader), ct.POINTER(SigStruct),
												ct.c_char_p, ct.c_char_p]
		self.dll.CsConvertFromSigHeader.restype = ct.c_int32
		

	
# # Callback Function Type
# if sys_plat == "win32":
# 	func_type = ct.WINFUNCTYPE
# else:
# 	# Untested!
# 	print('Untested callback type!')
# 	func_type = ct.CFUNCTYPE

#  BUG: func_type = ct.WINFUNCTYPE above causes python to crash - Justin 20200810
print('Untested callback type!')
func_type = ct.CFUNCTYPE

callbackFuncType = func_type(None, ct.c_void_p)

def checkerror(ErrorCode, exception=CompuScopeError, output=False):
	"""
	Raise exception with error string if i32ErrorCode<0.

	:param ErrorCode: error code
	:param exception: class of exception
	:param output: output success error codes too (True if debug flag is set)
	"""

	if ErrorCode < 0:
		raise exception(GetErrorString(ErrorCode) + " (Code {})".format(ErrorCode))
	elif output or debug:
		print("CompuScope: " + GetErrorString(ErrorCode) + " (Code {})".format(ErrorCode))


dll = DllContainer("CSSSM")


def Initialize():
	"""
	Initialize Gage Driver for further processing.
	"""
	res = dll.CsInitialize()
	checkerror(res)

class System(object):

	_handle = None

	def __init__(self, BoardType=0, Channels=0, SampleBits=0, Index=0, reset=True):
		self._id = Index
		
		self._handle = ct.c_ulong()      # raw format of ctypes.wintypes.HANDLE
		res = dll.CsGetSystem(ct.byref(self._handle), ct.c_uint32(BoardType),
									 ct.c_uint32(Channels),  ct.c_uint32(SampleBits), ct.c_int16(Index))
		checkerror(res)
		
		self.callback_c = {}  
		
		if reset:
			if debug:
				print('Reseting')
			self.Reset()    # on-board auto-calibration sequence


	def __del__(self):
		if debug:
			print("Deleting csapi.System");
		self.Close()

	def Close(self):
		if debug:
			print("Closing system")
			
		if self._handle is not None:
			res = dll.CsFreeSystem(self._handle)
			checkerror(res)
			del self._handle
			
			if debug:
				print("System Released")

	def GetInfo(self):
		"""
		Retrieves the static information about the CompuScope system.

		:returns: Structure that will be filled with the CompuScope
					system information.
		:rtype: SystemInfo class
		"""

		pSI = SystemInfo()
		res = dll.CsGetSystemInfo(self._handle, pSI)
		checkerror(res)

		return pSI


	def GetCaps(self, cap):
		"""
		Retrieves the capabilities of the CompuScope system in its
		current configuration.
		"""

		pSI = SystemInfo()
		pBuffer = ct.c_void_p()
		bufferSize = ct.c_uint32()
		res = dll.CsGetSystemCaps(self._handle, cap.value, pBuffer, ct.POINTER(bufferSize))
		checkerror(res)
		
		buffer = (ct.c_ubyte*pBuffer)()
		res = dll.CsGetSystemCaps(self._handle, cap.value, ct.POINTER(buffer), ct.POINTER(bufferSize))
		checkerror(res)
		#if cap == Caps.CLK_IN:
			
		
		raise NotImplementedError("Because of too many CapsId structures.")        

	def Do(self, action):
		"""
		Performs an operation on the CompuScope system.

		:param action: Requested action
		"""

		res = dll.CsDo(self._handle, ct.c_int16(action))
		checkerror(res)
		
	def Commit(self):
		self.Do(Action.COMMIT)
		
	def Start(self):
		self.Do(Action.START)
		
	def Force(self):
		self.Do(Action.FORCE)
		
	def Abort(self):
		self.Do(Action.ABORT)

	def Reset(self):
		self.Do(Action.RESET)

	def GetAcquisition(self, config=Config.CURRENT):
		data = AcquisitionConfig()
		res = dll.CsGet(self._handle, ct.c_int32(Index.ACQUISITION), ct.c_int32(config), ct.byref(data))
		checkerror(res)
		return data

	def GetChannel(self, channel, config=Config.CURRENT):
		data = ChannelConfig(channel_index=channel)
		res = dll.CsGet(self._handle, ct.c_int32(Index.CHANNEL), ct.c_int32(config), ct.byref(data))
		checkerror(res)
		return data
		
	def GetTrigger(self, config=Config.CURRENT):
		data = TriggerConfig()
		res = dll.CsGet(self._handle, ct.c_int32(Index.TRIGGER), ct.c_int32(config), ct.byref(data))
		checkerror(res)
		return data
	
	def Set(self, index, data):
		res = dll.CsSet(self._handle, ct.c_int32(index), ct.byref(data))
		checkerror(res)

	def SetAcquisition(self, **kwargs):
		data = AcquisitionConfig(**kwargs)
		self.Set(Index.ACQUISITION, data)

	def SetChannel(self, channel, **kwargs):
		data = ChannelConfig(channel_index=ct.c_uint32(channel), **kwargs)
		self.Set(Index.CHANNEL, data)
		
	def SetTrigger(self, **kwargs):
		data = TriggerConfig(**kwargs)
		self.Set(Index.TRIGGER, data)

	def GetStatus(self):
		"""
		 Returns the current acquisition status of the CompuScope system.

		:returns: System status
					0 - Ready for acquisition or data transfer. 
					1 - Waiting for trigger event.
					2 - CompuScope system has been triggered but is still busy acquiring.
					3 - Data transfer is in progress.
					4 - CompuScope on-board auto-calibration sequence is in progress.
		:rtype: int
		"""

		result = dll.CsGetStatus(self._handle)
		checkerror(result)

		return result        

	def Transfer(self, pInData):
		"""
		Transfers a specified number of samples from CompuScope on-board
		acquisition memory to a buffer, from a specified starting address.
		The method may also be used to transfer other information, such as
		time-stamp data.

		:param pInData: Pointer to the structure containing requested data
							transfer settings and data buffer pointer 
		:type pInData: In_Params_TransferData
		:returns: structure that is filled with actual data transfer settings
		:rtype: Out_Params_TransferData
		"""

		pOutData =  Out_Params_TransferData()
		res = dll.CsTransfer(self._handle, pInData, pOutData)
		checkerror(res)

		return pOutData
	
	def Download(self, channel, buffer_length, segment=1, start_address=0):
		import numpy as np
		
		data = np.zeros(buffer_length, dtype=np.int16)
		pInData = In_Params_TransferData(
			channel = channel,
			mode = 4, # all as int16
			segment = segment, # the one and only segment
			start_address = start_address, # first after trigger
			length = buffer_length,
			data_buffer = data.ctypes.data
		)
		pOutData = self.Transfer(pInData)
		if pOutData.actual_length < buffer_length:
			data = data[:pOutData.actual_length]
		
		return data

	def RegisterCallback(self, event, callback):
		cb_c = callbackFuncType(callback)
		self.callback_c[event] = cb_c
		res = dll.CsRegisterCallbackFnc(self._handle, int(event), cb_c)
		checkerror(res)

	def GetEventHandle(self, event):
		pEvent = ct.c_void_p()
		res = dll.CsGetEventHandle(self._handle, int(event), pEvent)
		checkerror(res)
		return pEvent.value


def GetErrorString(ErrorCode, BufferMax=64):
	"""
	Obtains a descriptive error string corresponding to the
	provided error code.

	:param ErrorCode: Error code to look up. 
	:param nBufferMax: Specifies the size of the buffer 
	:returns: error string
	"""

	pBuffer = ct.create_string_buffer(BufferMax)
	result = dll.CsGetErrorString(ErrorCode, pBuffer, BufferMax)

	if result < 0:
		raise CompuScopeError("No error string could be found to code {}.".format(ErrorCode))

	return pBuffer.value.decode()



def ConvertToSigHeader(SigStruct, Comment=None, Name=None):
	"""
	Creates a SIG file header from the supplied parameters.

	NOT TESTED.

	:param SigStruct: SigStruct structure which contains information
						about the file to be saved 
	:type SigStruct: SigStruct structure
	:param Comment: String to put into the comment field of the SIG file
					header. If None, a default string is used.
	:type Comment: str
	:param Name: String to put into the name field of the SIG file header.
					If None, a default string is used.
	:type Name: str
	:returns: SIG file header
	:rtype: DiskFileHeader structure
	"""

	pHeader = DiskFileHeader()
	checkerror(dll.CsConvertToSigHeader(pHeader, SigStruct, Comment, Name))

	return pHeader



def ConvertFromSigHeader(Header):
	"""
	Creates a SIG file header from the supplied parameters.

	NOT TESTED.

	:param Header: DiskFileHeader buffer read from a SIG file
	:type Header: DiskFileHeader structure
	:param BufferMax: maximum length of strings
	:type BufferMax: int
	:returns: tuple of
				- SigStruct structure which will be filled in by the driver
				- comment field from the SIG file header
				- field from the SIG file header
	:rtype: tuple((SigStruct, str, str))
	"""

	pSigStruct = SigStruct()
	pComment = ct.create_string_buffer(256)
	pName = ct.create_string_buffer(9)

	res = dll.CsConvertFromSigHeader(Header, pSigStruct, pComment, pName)
	checkerror(res)

	return (pSigStruct, pComment.value.decode(), pName.value.decode())

