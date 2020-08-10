# -*- coding: utf-8 -*-
from __future__ import division, print_function
import os
import fnmatch
from os import path
from datetime import datetime

def reset_timestamps_recursive(backup, root, channel):
	print('Scanning path {}'.format(backup))
	for pathname, dirnames, filenames in os.walk(backup):	
		if fnmatch.fnmatch(pathname, '*_CH{:02d}/Folder.00001'.format(channel)):
			print("Found channel #{} at {}:".format(channel, pathname))
			for filename in fnmatch.filter(filenames, 'AS_CH{:02d}-*.sig'.format(channel)):
				filepath = path.join(pathname, filename)

				runpath = path.relpath(pathname, backup)
				datadir = path.join(root, runpath)
				datapath = path.join(datadir, filename)

				if path.exists(datapath):
					print('Resetting timestamp of original "{}".'.format(datapath))
					
					atime = (datetime.now() - datetime.fromtimestamp(0)).total_seconds()
					mtime = os.path.getmtime( filepath )
					os.utime(datapath, (atime ,mtime))
					pass
				else:
					print('Can''t find original file {} for backup {}.'.format(datapath, filepath))	
		
if __name__ == '__main__':

	
	root = "E:/Data/2018/"
	backup = "E:/Backup/2018/"

#	root = "E:/Data/"
#	backup = "E:/Backup/"

	reset_timestamps_recursive(backup, root, 2)