from __future__ import division
import csapi
from time import sleep
import numpy as np
import win32event

csapi.Initialize()

gage = csapi.System(reset=False)

info = gage.GetInfo()

gage.SetAcquisition(
        i64SampleRate = int(80e6),
        u32ExtClk = int(80e6),
        u32Mode = csapi.Mode.QUAD,
        u32SegmentCount = 1,
        i64Depth = int(96e4),
        i64TriggerTimeout = -1, # Set to CS_TIMEOUT_DISABLE=-1
        i64SegmentSize = int(96e4),
        i32SampleOffset = -1
    )

gage.SetChannel(1, 
        u32Term = 1,                        # DC coupling
        u32Impedance = int(1e6),
        u32InputRange = int(4e3), # in [mV]
    )
    
gage.SetChannel(2, 
        u32Term = 1,                        # DC coupling
        u32Impedance = int(1e6),
        u32InputRange = int(4e3), # in [mV]
    )
    
gage.SetTrigger(
        u32Condition = 1, #Rising slope
        u32ExtTriggerRange = int(10e3), # Vpp range in [mV]
        u32ExtImpedance = int(1e6), # in Ohms
        u32ExtCoupling = 1, # DC coupling
        i32Source = csapi.TriggerSource.EXT,
        i32Level = 30 # Percentage of range/2
    )

gage.Do(csapi.Action.COMMIT)

gage.Do(csapi.Action.START)    # start acquisition
#gage.Do(csapi.Action.FORCE)    # emulate trigger event

def cbAcquire(cbInfo):
    print("END_BUSY!")

def cbTrigger(cbInfo):
    print("TRIGGERED!")

def cbTxfer(cbInfo):
    print("END_TXFER!")

#gage.RegisterCallback(csapi.AcquisitionEvent.TRIGGERED, cbTrigger)
gage.RegisterCallback(csapi.AcquisitionEvent.END_BUSY, cbAcquire)
gage.RegisterCallback(csapi.AcquisitionEvent.END_TXFER, cbTxfer)

eventAcquire = gage.GetEventHandle(csapi.AcquisitionEvent.END_BUSY)
print(eventAcquire)


print('Waiting for acquisition')
res = win32event.WaitForSingleObject(eventAcquire, 10000)
if res == win32event.WAIT_ABANDONED:
    print('abandoned')
elif res == win32event.WAIT_TIMEOUT:
    print('timeout')


# wait of end of acquisition
while gage.GetStatus() != 0:    # not ready for data transfer
    sleep(0.1)
print('Got acquisition')

##########
# get data
acquisition = gage.GetAcquisition(csapi.Config.ACQUIRED)
trigger = gage.GetTrigger(csapi.Config.ACQUIRED)

# time data
t = np.arange(acquisition.i64Depth) / (acquisition.i64SampleRate)

    # X data
channelx = gage.GetChannel(channel=1, config=csapi.Config.ACQUIRED)
x = np.zeros(acquisition.i64Depth, dtype=np.int16)
pInData = csapi.In_Params_TransferData(
            u16Channel = 1,
            u32Mode = 4,            # all as int16
            u32Segment = 1,         # the one and only segment
            i64StartAddress = 0,    # first after trigger
            i64Length = acquisition.i64Depth,
            pDataBuffer = x.ctypes.data
        )
gage.Transfer(pInData)
x = x/2**15 * channelx.u32InputRange / 2000.0   # int16 -> 2**15 for number

# Y data
channely = gage.GetChannel(channel=2, config=csapi.Config.ACQUIRED)
y = np.zeros(acquisition.i64Depth, dtype=np.int16)
pInData = csapi.In_Params_TransferData(
                u16Channel = 2,
                u32Mode = 4,            # all as int16
                u32Segment = 1,         # the one and only segment
                i64StartAddress = 0,    # first after trigger
                i64Length = acquisition.i64Depth,
                pDataBuffer = y.ctypes.data
            )
gage.Transfer(pInData)
y = y/2**15 * channely.u32InputRange / 2000.0   # int16 -> 2**15 for number

gage.close()

def printStruct(s):
	for field in s._fields_:
		print field[0], getattr(s, field[0])

channel = channelx

myHeader2 = csapi.SigFileHeader(
	name="Ch {:02d}".format(channel.u32ChannelIndex),
	sample_rate_index=31,
	operation_mode=2,
	trigger_depth=acquisition.i64Depth,
	trigger_slope=1,
	trigger_source=127,
	trigger_level=trigger.i32Level,
	sample_depth=acquisition.i64Depth,
	captured_gain=2,
	captured_coupling=channel.u32Term,
	ending_address=acquisition.i64Depth-1,
	trigger_time=0,
	trigger_date=0,
	trigger_coupling=trigger.u32ExtCoupling,
	trigger_gain=3,
	board_type=info.u32BoardType,
	resolution_12_bits=1,
	sample_offset=-1,
	sample_resolution=-8192,
	sample_bits=acquisition.u32SampleBits,
	imped_a=0,
	imped_b=16,
	external_tbs=1e9/acquisition.u32ExtClk,
	external_clock_rate=acquisition.u32ExtClk,
	record_depth=acquisition.i64Depth
)

gage.close()