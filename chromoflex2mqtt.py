#
# Written and (C) 2015 by Oliver Wagner <owagner@tellerulam.com>
# Provided under the terms of the MIT license
#
# Requires:
# - PySerial
# - Eclipse Paho for Python - http://www.eclipse.org/paho/clients/python/
#

import argparse
import logging
import logging.handlers
import time
import json
import socket
import sys
import serial
import colorsys
from numbers import Number
import paho.mqtt.client as mqtt

version="0.2"

parser = argparse.ArgumentParser(description='Control a Chromoflex II (RS232/USP3) via MQTT')
parser.add_argument('--mqtt-host', default='localhost', help='MQTT server address. Defaults to "localhost"')
parser.add_argument('--mqtt-port', default='1883', type=int, help='MQTT server port. Defaults to 1883')
parser.add_argument('--mqtt-topic', default='chromo/', help='Topic prefix to be used for subscribing/publishing. Defaults to "chromo/"')
parser.add_argument('--serial', help='Serial device name or URL', required=True)
parser.add_argument('--defaddr', default=0, type=int, help='Default USP3 address (def: 0 == broadcast)')
parser.add_argument('--log', help='set log level to the specified value. Defaults to WARNING. Try DEBUG for maximum detail')
parser.add_argument('--syslog', action='store_true', help='enable logging to syslog')
args=parser.parse_args()

if args.log:
    logging.getLogger().setLevel(args.log)
if args.syslog:
    logging.getLogger().addHandler(logging.handlers.SysLogHandler())

topic=args.mqtt_topic
if not topic.endswith("/"):
	topic+="/"

logging.info('Starting chromoflex2mqtt V%s with topic prefix \"%s\"' %(version, topic))

#
# USP3 command generator
#

def update_crc(d):
	global usp_crc
	usp_crc^=d
	for x in range(0,8):
		if usp_crc&1:
			usp_crc>>=1 
			usp_crc^=0xA001
		else:
			usp_crc>>=1
			
def serial_send_raw(d):
	ser.write(chr(d))
	print("sending raw data ",chr(d))

def serial_send_cooked(d):
	update_crc(d)
	if d==0xca:
		serial_send_raw(0xcb)
		serial_send_raw(0)
	elif d==0xcb:
		serial_send_raw(0xcb)
		serial_send_raw(1)
	else:
		serial_send_raw(d)

def sendcmd(cmd,addr,data):
	global usp_crc
	serial_send_raw(0xca)
	usp_crc=0x173f
	serial_send_cooked((addr>>16)&0xff)
	serial_send_cooked((addr>>8)&0xff)
	serial_send_cooked((addr>>0)&0xff)
	datalen=len(data)
	serial_send_cooked((datalen>>8)&0xff)
	serial_send_cooked((datalen>>0)&0xff)
	serial_send_cooked(cmd);
	for b in data:
		serial_send_cooked(b);
	crc=usp_crc
	serial_send_cooked((crc>>8)&0xff)
	serial_send_cooked((crc>>0)&0xff)
	ser.flush()

#
# MQTT command handling
#

class State:
	HSV=0
	RGB=1
	def __init__(self,addr):
		self.bright=0
		self.hue=0
		self.sat=0
		self.addr=addr
		self.mode=State.HSV
		self.on=True
		self.dontSync=False
		self.prog=True # So we turn off effects mode on next send
		
	def calcrgb(self):
		if self.mode==State.HSV:
			r,g,b=colorsys.hsv_to_rgb(self.hue/65535.0,1.0-self.sat/254.0,self.bright/254.0)
			self.r=int(r*255)
			self.g=int(g*255)
			self.b=int(b*255)
		
	def sync(self):
		if not self.on:
			sendcmd(0x7e,self.addr,[4,0,0,0])
			return
		self.calcrgb()
		print("syncing",self.r,self.g,self.b)
		if self.prog:
			sendcmd(0x7e,self.addr,[18,1])
			self.prog=False
		sendcmd(0x7e,self.addr,[4,self.r,self.g,self.b])
		
	def checksync(self):
		if not self.dontSync:
			self.sync()
		else:
			self.dontSync=False

stateByAddr={}

def rangecheck(n,v,f,t):
	if v<f or v>t:
		raise ValueError("%s must be %u..%u" % (n,f,t))

def getstate(addr):
	if not addr in stateByAddr:
		stateByAddr[addr]=State(addr)
	return stateByAddr[addr]

def processItemSet(addr,itemname,val):
	s=getstate(addr)
	if itemname=="hue":
		rangecheck("hue",val,0,65535)
		s.mode=State.HSV
		s.hue=val
	elif itemname=="sat":
		rangecheck("sat",val,0,254)
		s.mode=State.HSV
		s.sat=val
	elif itemname=="bri":
		rangecheck("bri",val,0,254)
		s.mode=State.HSV
		s.bright=val
	elif itemname=="red":
		rangecheck("red",val,0,255)
		s.mode=State.RGB
		s.red=val
	elif itemname=="green":
		rangecheck("green",val,0,255)
		s.mode=State.RGB
		s.green=val
	elif itemname=="blue":
		rangecheck("blue",val,0,255)
		s.mode=State.RGB
		s.green=val
	elif itemname=="ct":
		# We really can't do different whites
		s.mode=State.HSV
		s.sat=254
	elif itemname=="on":
		if val==0:
			s.on=False
		else:
			s.on=True
	elif itemname=="effect":
		rangecheck("effect",val,0,9)
		if val!=0:
			s.prog=True
			s.dontSync=True
			sendcmd(0x7e,addr,[18,0])
			sendcmd(0x7e,addr,[21,0,(val-1)*3+200])
	elif itemname=="increment":
		rangecheck("increment",val,0,255)
		sendcmd(0x7e,addr,[8,val,val,val])
	elif itemname=="incrementr":
		rangecheck("incrementr",val,0,255)
		sendcmd(0x7e,addr,[8,val])
	elif itemname=="incrementg":
		rangecheck("incrementg",val,0,255)
		sendcmd(0x7e,addr,[9,val])
	elif itemname=="incrementb":
		rangecheck("incrementb",val,0,255)
		sendcmd(0x7e,addr,[10,val])
	else:
		raise ValueError("Invalid item name %s" % itemname)

def handleset(tp,msg):
	print(tp)
	print(msg)
	addr=args.defaddr
	# Check whether the next element is an address
	try:
		addr=int(tp[0],0)
		tp.pop(0)
	except:
		# Apparently not
		addr=args.defaddr
	if addr<0 or addr>0xffffff:
		raise ValueError("Address must be 0..0xffffff")

	# Now see whether we have a subtopic 
	if len(tp)>0:
		processItemSet(addr,tp[0],int(msg,0))
	else:
		# Either a single value, or a JSON object
		js=json.loads(msg)
		print("js is",js)
		if isinstance(js,Number):
			if js<1:
				processItemSet(addr,"on",0)
			else:
				getstate(addr).on=True
				processItemSet(addr,"bri",js)
		else:
			for item,val in js.items():
				processItemSet(addr,item,val)
			
	getstate(addr).checksync()

def handlecommand(cmd):
    print(cmd)

def msghandler(mqc,userdata,msg):
	try:
		global topic
		if msg.retain:
			return
		tp=msg.topic[len(topic):].split("/")
		if tp[0]=="set":
			tp.pop(0)
			handleset(tp,msg.payload)
		else:
			logging.warning("Unparsable topic %s" % msg.topic)
	except Exception as e:
		logging.warning("Error processing message %s" % e)

def connecthandler(mqc,userdata,rc):
    logging.info("Connected to MQTT broker with rc=%d" % (rc))
    mqc.subscribe(topic+"set/#",qos=0)
    mqc.will_set(topic+"connected",0,qos=2,retain=True)
    mqc.publish(topic+"connected",2,qos=1,retain=True)

def disconnecthandler(mqc,userdata,rc):
    logging.warning("Disconnected from MQTT broker with rc=%d" % (rc))
    time.sleep(5)

mqc=mqtt.Client()
mqc.on_message=msghandler
mqc.on_connect=connecthandler
mqc.on_disconnect=disconnecthandler
mqc.connect(args.mqtt_host,args.mqtt_port,60)

ser=serial.serial_for_url(args.serial)
ser.baudrate=9600
ser.bytesize=serial.EIGHTBITS
ser.parity=serial.PARITY_NONE
ser.stopbits=serial.STOPBITS_ONE

mqc.loop_forever()
