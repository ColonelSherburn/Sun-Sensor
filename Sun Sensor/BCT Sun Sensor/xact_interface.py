import serial
import sys
import time
import struct
from collections import namedtuple
import numpy as np 
import matplotlib.pyplot as plt 
from matplotlib import style 
import pandas as pd 
from openpyxl import load_workbook 

plt.axis()
plt.ion()
plt.title('Diode Readings')
plt.xlabel('Time (sec)')
plt.ylabel('Diode Reading')
style.use('ggplot')

def calcCRC8(crc8, data):
        polynomial = 0x1070 << 3

        for entry in data:
                data = crc8 ^ entry
                data = data << 8 & 0xFFFF
                for i in range(8):
                        if (data & 0x8000 != 0):
                                data = data ^ polynomial
                        data = data << 1 & 0xFFFF 
                                
                crc8 = (data >> 8) & 0xFF
                
        return crc8
        
def findDataMsg(rawData, idString):
        for i in range(0, len(rawData)-1):
                if (rawData[i:i+2] == idString):
                        msgStart = i
                        # Parse message length
                        msgLength = struct.unpack(">H",rawData[msgStart+4:msgStart+6])[0]
                        dataBytes = rawData[msgStart+6:msgStart+6+msgLength]
                        
                        # Parse CRC
                        crcRcvd = rawData[msgStart+6+msgLength]
                        crc8 = 0xFF
                        crc8 = calcCRC8(crc8, rawData[msgStart:-1])
                        #print("Received and calculated CRC:", crcRcvd, crc8)
                        
                        if (int(crc8) == crcRcvd):
                                return True, dataBytes
                        else:
                                return False, b''

        return False, b''

def parseDataEntry(rawData, dataType):
        if (dataType == 'uint8'):
                return struct.unpack('B', rawData)[0]
        elif (dataType == 'int16'):
                return struct.unpack('>h', rawData)[0]
        elif (dataType == 'uint16'):
                return struct.unpack('>H', rawData)[0]
                
# Notes:
# XACT processor is big-endian
# Commands should be at least 6 msec apart
# See XACT ICD Table 9 for read addresses (reference ICD Addendum Sec 4 for relevant telemetry packages)

# XACT interface parameters
writeCmdID = b'\xEB'
readCmdID = b'\xEC'
readWithHeadAndCRCCmdId = b'\xED'
syncID = b'\x1A\xCF'
headerLength = 6
writeAddr = 0x0000
readAddr = 0x420
readLength = 573-32+1

# Relevant telemetry
TelemPoint = namedtuple('TelemPoint', ['name', 'loc', 'size', 'type'])
rw1OpMode = TelemPoint('RW 1 Operating Mode', 0x4AF, 1, 'uint8')
rw2OpMode = TelemPoint('RW 2 Operating Mode', 0x4B0, 1, 'uint8')
rw3OpMode = TelemPoint('RW 3 Operating Mode', 0x4B1, 1, 'uint8')
rw4OpMode = TelemPoint('RW 4 Operating Mode', 0x4B2, 1, 'uint8')
rw1Speed = TelemPoint('RW 1 Meas Speed', 0x45B, 2, 'int16')
rw2Speed = TelemPoint('RW 2 Meas Speed', 0x45D, 2, 'int16')
rw3Speed = TelemPoint('RW 3 Meas Speed', 0x45F, 2, 'int16')
rw4Speed = TelemPoint('RW 4 Meas Speed', 0x461, 2, 'int16')
ss1Counts = TelemPoint('SS Diode 1 Count', 0x57D, 2, 'uint16')
ss2Counts = TelemPoint('SS Diode 2 Count', 0x57F, 2, 'uint16')
ss3Counts = TelemPoint('SS Diode 3 Count', 0x581, 2, 'uint16')
ss4Counts = TelemPoint('SS Diode 4 Count', 0x583, 2, 'uint16')
telemPts = [rw1OpMode, rw2OpMode, rw3OpMode, rw4OpMode, 
            rw1Speed, rw2Speed, rw3Speed, rw4Speed,
            ss1Counts, ss2Counts, ss3Counts, ss4Counts]
telemData = {rw1OpMode.name: 0, rw2OpMode.name: 0, rw3OpMode.name: 0, rw4OpMode.name: 0, 
            rw1Speed.name: 0, rw2Speed.name: 0, rw3Speed.name: 0, rw4Speed.name: 0,
            ss1Counts.name: 0, ss2Counts.name: 0, ss3Counts.name: 0, ss4Counts.name: 0}


# Check input arguments 
if (len(sys.argv) != 2):
                print("Error: Incorrect number of arguments.")
                sys.exit()

# Open serial interface
serPort = sys.argv[1]
ser = serial.Serial(port = serPort, baudrate = 115200, parity = serial.PARITY_NONE, stopbits = serial.STOPBITS_ONE, timeout = 0)

diode_readings = {'diode1': [], 'diode2': [], 'diode3': [], 'diode4': []}

# time for plotting
start_time = time.time()
time_readings = []
# Read data from XACT (data updated at 5 Hz)
for i in range(10):
        # Request data read
        readCmd = readWithHeadAndCRCCmdId + struct.pack('>H', readAddr) + struct.pack('>H', readLength)
        ser.write(readCmd)
        
        ## Check for data
        time.sleep(0.5)
        readData = ser.read(1000)
        
        print("Number of bytes read:", len(readData))
        if (len(readData) > 0):
                # Find data message
                msgFound, rcvdMsg = findDataMsg(readData, syncID)
                
                # Parse data
                if (msgFound):
                        for i in range(0, len(telemPts)):
                                telemData[telemPts[i].name] = parseDataEntry(rcvdMsg[telemPts[i].loc - readAddr:telemPts[i].loc - readAddr + telemPts[i].size], telemPts[i].type)
                        #print(readData)
                                print(telemPts[i].name, ":", telemData[telemPts[i].name])
                        
                        time_readings.append(round((time.time() - start_time), 3))
                        diode_readings['diode1'].append(telemData['SS Diode 1 Count'])
                        diode_readings['diode2'].append(telemData['SS Diode 2 Count'])
                        diode_readings['diode3'].append(telemData['SS Diode 3 Count'])
                        diode_readings['diode4'].append(telemData['SS Diode 4 Count'])
                else:
                        #print(readData)
                        print("Data message not found")


                                
        # Command RW 1 to EXTERNAL operating mode (if not already in EXTERNAL)
        if (telemData['RW 1 Operating Mode'] != 2):
                
                rw1OpModeCmd = writeCmdID + struct.pack('>H', writeAddr) + struct.pack('>H',4) + struct.pack("=BBBB", 7, 2, 0, 2)
                ser.write(rw1OpModeCmd)
                print("Updating RW 1 operating mode")
                #rw1OpModeCmd = struct.pack("=BBBB", 7, 2, 1, 2)
                #print(rw1OpModeCmd)
                #ser.write(rw1OpModeCmd)
                #time.sleep(0.1)
        #    a = 1
        # dynamic plotting
        style.use('ggplot')
        colors = {'diode1' : 'b', 'diode2': 'r', 'diode3': 'g', 'diode4': 'c'}
        for diode in diode_readings:
            plt.plot(time_readings, (diode_readings[diode]), color = colors[diode])
        
        plt.legend(['diode1', 'diode2', 'diode3', 'diode4'], loc = 1)
        plt.pause(0.01)
               
ser.close() # close the port so the program can be run again 

# create a DataFrame out of the dictionary

diode_readings['Time'] = time_readings
df = pd.DataFrame(diode_readings)
df.set_index('Time', inplace=True)
print(df)
'''
# List of the averages for the test. 
averages = [df[key].describe()['mean'] for key in df]
indexes = df.index.tolist()
indexes.append('mean')
df.reindex(indexes)
# Adding the mean row to the bottom of the DataFrame

i = 0
for key in df:
	df.set_value('mean', key, averages[i])
	i += 1

# Writing the data to an Excel file. 
# If the Excel file already exists, add another sheet.
try:
	book = load_workbook('DiodeReadings1.xlsx')
	writer = pd.ExcelWriter('DiodeReadings1.xlsx', engine='openpyxl')
	writer.book = book
	writer.sheets = dict((ws.title, ws) for ws in book.worksheets)
	df.to_excel(writer, '90 Sun 0 Az') # Change the name of the sheet to correct configuration.

# If the Excel file does not exist, it will be created. 	
except: 
	writer = pd.ExcelWriter('DiodeReadings1.xlsx', engine='openpyxl')
	df.to_excel(writer, '90 Sun 180 Az') # Change the name of the sheet to correct configuration.

writer.save()
'''





