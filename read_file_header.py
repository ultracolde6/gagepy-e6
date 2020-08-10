from __future__ import division
import csapi

import Tkinter, tkFileDialog
import binascii
import ctypes as ct

import numpy as np
import matplotlib.pyplot as plt


root = Tkinter.Tk()
root.withdraw()

file_path = tkFileDialog.askopenfilename()

#header = csapi.DiskFileHeader()
myHeader = csapi.SigFileHeader()

with open(file_path, "rb") as f:
	f.readinto(myHeader)
	sample_data = np.fromfile(f, dtype=np.int16, count=myHeader.sample_depth)
#	header = csapi.DiskFileHeader.from_buffer_copy(data)

#(sigStruct,comment,name) = csapi.ConvertFromSigHeader(header)

del root

def printStruct(s):
	for field in s._fields_:
		print field[0], getattr(s, field[0])

#myHeader = csapi.SigFileHeader.from_buffer_copy(data)
	
printStruct(myHeader)

#~ myHeader2 = csapi.SigFileHeader(
	#~ name="Ch 01",
	#~ comment=comment,	
	#~ sample_rate_index=31,
	#~ operation_mode=2,
	#~ trigger_depth=960000,
	#~ trigger_slope=1,
	#~ trigger_source=127,
	#~ trigger_level=20,
	#~ sample_depth=960000,
	#~ captured_gain=2,
	#~ captured_coupling=1,
	#~ ending_address=960000-1,
	#~ trigger_time=0,
	#~ trigger_date=0,
	#~ trigger_coupling=1,
	#~ trigger_gain=3,
	#~ board_type=8227,
	#~ resolution_12_bits=1,
	#~ sample_offset=-1,
	#~ sample_resolution=-8192,
	#~ sample_bits=14,
	#~ imped_a=0,
	#~ imped_b=16,
	#~ external_tbs=12.5,s
	#~ external_clock_rate=80e6,
	#~ record_depth=960000
#~ )

pack_date = myHeader.trigger_date
pack_time = myHeader.trigger_time

day = pack_date & 0b11111
month = (pack_date >> 5) & 0b1111
year = (pack_date >> 9) + 1980

second = (pack_time & 0b11111)*2
minute = (pack_time >> 5) & 0b111111
hour = (pack_time >> 11)

print('Date: {}/{:02d}/{}'.format(month,day,year))
print('Time: {:d}:{:02d}:{:02d}'.format(hour,minute,second))

gain_range = (20, 10, 4, 2, 1, .4, .2)
scaleVpp = gain_range[myHeader.captured_gain]

t = np.arange(myHeader.sample_depth) / (myHeader.external_clock_rate)
scaled_data= (myHeader.sample_offset - sample_data)/myHeader.sample_resolution * scaleVpp / 2

plt.plot(t, scaled_data)
plt.show(block=True)



