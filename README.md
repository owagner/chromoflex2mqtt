chromoflex2mqtt
===============

  Written and (C) 2015 Oliver Wagner <owagner@tellerulam.com> 
  
  Provided under the terms of the MIT license.


Overview
--------
Gateway to control a Barthelme Chromoflex II RGB LED controller via
MQTT. The controller has a RS232 interface and supports a simple
serial protocol called USP3.

This module is intended as a building block in heterogenous smart home environments where 
an MQTT message broker is used as the centralized message bus.
See https://github.com/mqtt-smarthome for a rationale and architectural overview.


Topic structure
===============
chromoflex2mqtt follows the mqtt-smarthome topic structure with a top-level prefix 
and the only support function code _set_. Since the serial communication
with the controller is strictly unidirectional, no status reports can be
generated.

chromoflex2mqtt tries to provide an API somewhat similiar to hue2mqtt,
offering control via the HSV color model.

Since multiple controllers can be on a single RS232 bus, it's possibly to
specify an address in all set commands. If no address is specified, the
default address specified as a module parameter is used. This address
defaults to "0", which is the broadcast address which controls all controllers.

Setting state is possible in one of three ways:    

Method 1: Publishing a simple integer value to
    
    chromo/set[/addr]>
    
will for value=0 turn off all channels and for values > 0 turn the controller on 
and set the brightness to the given value.

Method 2: Publishing a JSON encoded object to

    chromo/set[/addr]>

will set multiple parameters of the controller. The field names are described
below.

Method 3: Publishing a simple value to

	chromo/set[/addr]>/<fieldname>
	
will distinctly set a single fieldnames to the simple value.

The fields "bri", "hue", "sat", and "ct" have variants with a "_inc" suffix
which accept a relative value. For example, setting "bri_inc" to "5" will increase
the brightness by 5, setting "bri_inc" to "-5" will decrease the brightness by 5.
The values will clip properly within their allowed range.


Dependencies
------------
* PySerial
* Eclipse Paho for Python - http://www.eclipse.org/paho/clients/python/


History
-------
* 0.2 - 2015/12/05 - owagner
  - initial public release
