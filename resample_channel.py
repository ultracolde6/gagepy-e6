from __future__ import division, print_function
import numpy as np
import csapi
import os
import matplotlib.pyplot as plt
from math import floor
import fnmatch
from os import makedirs, path
from datetime import datetime
import signal, time
import sys

from gage_util import e3decimate

# This script recursively scans through old GageScope signal files, and downsamples the selected channel to a lower sample rate. 
# The original file can be moved to a backup location

terminate = False                            

def signal_handling(signum,frame):           
    global terminate
    print('Interrupted!')
    terminate = True                         

signal.signal(signal.SIGINT,signal_handling) 
	
	
sample_rates = (1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 1e3, 2e3, 5e3, 1e4, 2e4, 5e4, 1e5, 2e5, 5e5,
		1e6, 2e6, 2.5e6, 5e6, 1e7, 1.25e7, 2e7, 2.5e7, 3e7, 4e7, 5e7, 6e7, 6.5e7, 8e7, 
		1e8, 1.2e8, 1.25e8, 1.3e8, 1.5e8, 2e8, 2.5e8, 3e8, 5e8, 1e9, 2e9, 4e9, 5e9, 8e9, 1e10)

def resample_file(filepath, resample_rate, target=None, moveorig=None):

	if target is None:
		target = filepath

	header = csapi.SigFileHeader()
	with open(filepath, 'rb') as f:
		f.readinto(header)
		data = np.fromfile(f, dtype=np.int16)

	ext_clk_rate = header.external_clock_rate	
	if header.sample_rate_index < 47:
		sample_rate = sample_rates[header.sample_rate_index]
	else:
		sample_rate = ext_clk_rate

	decimation_factor =  int(floor(sample_rate / resample_rate))
	#~ print('Decimation factor: {:d}'.format(decimation_factor))
	if decimation_factor > 1:
		filtered = e3decimate(data, decimation_factor, n=6).astype(np.int16)
	
		new_sample_rate = sample_rate / decimation_factor
		new_ext_clk_rate = header.external_clock_rate / decimation_factor
		
		try:
			header.sample_rate_index = sample_rates.index(new_sample_rate)
		except ValueError:
			header.sample_rate_index = 47 #External clock index
			
		header.external_tbs=1e9/new_ext_clk_rate
		header.external_clock_rate=new_ext_clk_rate
		
		header.trigger_depth=len(filtered)
		header.sample_depth=len(filtered)
		header.ending_address=len(filtered)-1
		header.record_depth=len(filtered)
		
	else:
		filtered = data
		
	atime = (datetime.now() - datetime.fromtimestamp(0)).total_seconds()
	mtime = os.path.getmtime( filepath )

	if moveorig is not None:
		os.rename(filepath, moveorig)

	with open(target, 'wb') as f:
		f.write(header)
		f.write(filtered.astype(np.int16).tobytes())
		
	os.utime(target, (atime ,mtime))

	return (data, filtered, sample_rate, decimation_factor)

def read_file_samplerate(filepath):
	header = csapi.SigFileHeader()
	with open(filepath, 'rb') as f:
		f.readinto(header)

	ext_clk_rate = header.external_clock_rate	
	if header.sample_rate_index < 47:
		sample_rate = sample_rates[header.sample_rate_index]
	else:
		sample_rate = ext_clk_rate
		
	return sample_rate

def plot_resample(data, filtered, sample_rate, decimation_factor):
	
	plt.figure()
	
	t = np.arange(0,len(data)) / sample_rate
	
	plt.plot(t, data)
	plt.plot(t[::decimation_factor], filtered)
	
	plt.show(block = True)
	
def resample_folder(path, resample_rate):
	print('Scanning path {}'.format(path))
	for filename in os.listdir(path):
		if fnmatch.fnmatch(filename, 'AS_CH*.sig'):
			filepath = path.join(path, filename)			
			sample_rate = read_file_samplerate(filepath)
			if sample_rate > resample_rate:
				print('Resampling {} from {:.1f}MHz...'.format(filename, sample_rate/1e6))
				#resample_file(filepath, resample_rate)
			else:
				print('Skipping {} with sample rate {:.1f}MHz.'.format(filename, sample_rate/1e6))

def resample_channel_recursive(root, channel, resample_rate, backup=None):
	print('Scanning path {}'.format(root))
	for pathname, dirnames, filenames in os.walk(root):
		if terminate:
			break
			
		if fnmatch.fnmatch(pathname, '*_CH{:02d}/Folder.00001'.format(channel)):
			print("Found channel #{} at {}:".format(channel, pathname))
			 
			for filename in fnmatch.filter(filenames, 'AS_CH{:02d}-*.sig'.format(channel)):
				if terminate:
					break
				
				
				filepath = path.join(pathname, filename)
				sample_rate = read_file_samplerate(filepath)
				if sample_rate > resample_rate:
					print('Resampling {} from {:.1f}MHz...'.format(filename, sample_rate/1e6))

					if backup is not None:
						runpath = path.relpath(pathname, root)
						backupdir = path.join(backup, runpath)
						backuppath = path.join(backupdir, filename)
	
						print('Moving original to backup location "{}".'.format(backuppath))					
						if not path.exists(backupdir):
							makedirs(backupdir)
					else:
						backuppath = None

					resample_file(filepath, resample_rate, moveorig=backuppath)
					
				else:
					print('Skipping {} with sample rate {:.1f}MHz.'.format(filename, sample_rate/1e6))	
	
if __name__ == '__main__':
	
	# First command line argument is the channel number. This is required.
	channel = int(sys.argv[1])
	
	# Hard coded data root and backup root
	root = "/mnt/shotnoise/Data/"
	backup = "/mnt/shotnoise/ResampleBackup/"
	#root = "/mnt/dataraid/Data/"
	#backup = "/mnt/dataraid/Backup/"

	# If provided, the second argument is a subpath to scan under the root.
	if len(sys.argv) > 2:
		year = sys.argv[2]

		root = path.join(root, year)
		backup = path.join(backup, year)

	print("Channel: ", channel)
	print("Data Root: ", root)
	print("Backup Root: ", backup)
	resample_channel_recursive(root, channel=channel, resample_rate=2e6, backup=backup)

## code to resample and display a test trace
#	filename = 'AS_CH02-00001.sig' #sys.argv[1]
#	target = 'AS_CH02-00001.sig2' #sys.argv[2]
#	data, filtered, sample_rate, decimation_factor = resample_file(filename, 2e6, target=target)
#	plot_resample(data, filtered, sample_rate, decimation_factor)