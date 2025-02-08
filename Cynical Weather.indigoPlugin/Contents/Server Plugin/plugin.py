#
# Weather-related plugin services.
#
# Copyright 2013-2016 Perry The Cynic. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#	http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import time
import datetime

import asyn
import forecast
import astro

import cyin.devstate
from cyin import iom, plug
from cyin import log, debug, error
from cyin.asynplugin import action
from cyin.check import *


MIN_REFRESH = 5		# enforced minimum minutes between update calls per location


#
# Common server snapshot data device
#
class ForecastDevice(cyin.devstate.Device):

	conditions = cyin.DeviceState(type=str)
	temp = cyin.DeviceState(type=float)
	feelslike = cyin.DeviceState(type=float)
	dew = cyin.DeviceState(type=float)
	pressure = cyin.DeviceState(type=float, format=" mb")
	humidity = cyin.DeviceState(type=float, format="%")
	visibility = cyin.DeviceState(type=float, format=" mi")
	cloudcover = cyin.DeviceState(type=float, format="%")
	windspeed = cyin.DeviceState(type=float, format=" mph")
	windgust = cyin.DeviceState(type=float, format=" mph")
	winddir = cyin.DeviceState(type=float, format="\xb0")
	precip = cyin.DeviceState(type=float, format=" in")
	precipprob = cyin.DeviceState(type=float, format="%")
	icon = cyin.DeviceState(type=str)
	moonphase = cyin.DeviceState(type=float)
	uvindex = cyin.DeviceState(type=float)
	solarradiation = cyin.DeviceState(type=float, format=" W/m^2")
	solarenergy = cyin.DeviceState(type=float, format=" MJ/m^2")
	severerisk = cyin.DeviceState(type=int)
	data = cyin.DeviceState(type=str)
	
	alert = cyin.DeviceState(type=str)
	alert_url = cyin.DeviceState(type=str)

	def updateReading(self, reading):
		def update(name, op=lambda s: s):
			if hasattr(reading, name):
				value = getattr(reading, name)
				#debug(f"update {name} from {value}")
				if value is not None:
					setattr(self, name, op(value))
		update("summary")
		update("conditions")
		update("temp", lambda s: round(s, 1))
		update("feelslike", lambda s: round(s, 1))
		update("tempmin", lambda s: round(s, 1))
		update("tempmax", lambda s: round(s, 1))
		update("feelslikemin", lambda s: round(s, 1))
		update("feelslikemax", lambda s: round(s, 1))
		update("dew", lambda s: round(s, 1))
		update("pressure")
		update("humidity", lambda s: round(s, 1))
		update("visibility", lambda s: round(s, 1))
		update("cloudcover")
		update("windspeed")
		update("windgust")
		update("winddir")
		update("precip")
		update("precipprob")
		update("icon")
		update("moonphase")
		update("uvindex")
		update("solarradiation")
		update("solarenergy")
		update("severerisk")
	
	def updateAlerts(self, alerts):
		now = datetime.datetime.now()
		debug(f"alerts={alerts}")
		alerts = [alert for alert in alerts if alert.ends >= now]
		debug(f"filtered alerts={alerts}")
		self.alert = '; '.join([alert.headline for alert in alerts])
		self.alert_url = '; '.join([alert.link for alert in alerts if alert.link])


#
# A geographic location collecting and holding a full server data set.
# Its Indigo properties represent present-time values.
#
class Location(ForecastDevice):
	config_version = 3
	
	latitude = cyin.PluginProperty(type=float, required=False, check=[check_range(-90,90)])
	longitude = cyin.PluginProperty(type=float, required=False, check=[check_range(-180,180)])
	polling = cyin.PluginProperty(type=int, required=False, check=[check_range(min=MIN_REFRESH)])
	units = cyin.PluginProperty(type=str)
	rawdata = cyin.PluginProperty(type=bool)

	_poll_timer = None
	_last_update = 0
	lastReading = None

	def start(self):
		super(Location, self).start()
		self.setup()

	def setup(self, ctx=None):
		self.forecast = forecast.Forecast(cyin.plugin)
		self.forecast.apikey = cyin.plugin.apikey
		self.forecast.location = self._location()
		self.forecast.units = self.units
		self.forecast.user_agent = f"Cynical-Weather/{self.plugin.version}"
		self.set_display_address(astro.s_location(*self.forecast.location.lat_lon))
		if self.polling:
			self.update()
		else:
			self.proceed("ready")	# (passive mode)

	def stop(self):
		if self._poll_timer:
			self._poll_timer.cancel()
			self._poll_timer = None
		super(Location, self).stop()

	def update(self, ctx=None):
		""" Manage automatic timed polling updates. """
		if self.polling:
			self._poll_timer = cyin.plugin.schedule(self.update, after=self.polling * 60)
		self.poll(force=not ctx)

	def poll(self, force=False):
		""" Explicitly poll for new data about this location.

			This is clamped to no more than once per MIN_REFRESH minutes to avoid
			accidentally hitting the daily request limit.
		"""
		now = time.time()
		if not force and self._last_update + MIN_REFRESH * 60 > now:
			return error(self.name, "ignoring update request within {MIN_REFRESH} minutes of last one")
		self._last_update = now
		def updated(ctx, data=None):
			if ctx.error:
				return self.fail_hard(ctx)
			elif ctx.state == 'error':
				return self.fail_hard(f"weather service error: {data.n_status} {data.v_status}")
			elif ctx.state == 'reading':
				self.lastReading = data
				debug(self.name, "updated")
				self.data = data.raw.decode("utf8") if self.rawdata else "N/A"
				self.updateAlerts(data.alerts)
				self.updateReading(data.current)
				for fc in Forecast.all():
					fc.updateForecast(data)
				self.proceed("ready", recovered=True)
		self.forecast.poll(callout=updated)

	def _location(self):
		""" Return a forecast.Location object from either explicit data or the default location. """
		if self.latitude and self.longitude:
			return forecast.Location(self.latitude, self.longitude)
		else:
			return forecast.Location(*indigo.server.getLatitudeAndLongitude())

	@cyin.action
	def update_data(self, action):
		self.poll()


#
# A temporal slice of an existing data set.
#
class Forecast(ForecastDevice):
	location = cyin.PluginProperty(type=cyin.device)
	distance = cyin.PluginProperty(type=int, check=[check_range(0, 50)])
	
	# Summary (aka description) and the min/max temperatures are only reported for forecasts.
	# Well, for hourly and daily reports, which amounts to the same for us.
	summary = cyin.DeviceState(type=str)
	tempmin = cyin.DeviceState(type=float)
	tempmax = cyin.DeviceState(type=float)
	feelslikemin = cyin.DeviceState(type=float)
	feelslikemax = cyin.DeviceState(type=float)

	def start(self):
		super(Forecast, self).start()
		self.set_hostdev(self.location)
		self.setup()

	def setup(self, ctx=None):
		self.set_display_address(f"{self.hostdev.name} + {self.distance} {self.units}")
		if self.hostdev.lastReading:
			self.updateForecast(self.hostdev.lastReading)
		self.proceed("ready")

	def updateForecast(self, reading):
		data = reading.getPoint(self.distance, self.units)
		if data:
			debug(self.name, "updated for", time.ctime(data.datetimeEpoch))
			self.updateReading(data)
			self.updateAlerts(reading.alerts)
		else:
			error(f"{self.name}: {self.hostdev.name} has no reading for {self.distance} {self.units} ahead")

	@cyin.action
	def update_data(self, action):
		self.hostdev.poll()


class HourForecast(Forecast):
	units = 'hours'


class DayForecast(Forecast):
	config_version = 2
	
	units = 'days'


#
# A (window et al) orientation in space. This is what we orient the Sun against.
# Actual updates are driven by a central timer.
#
BELOW_HORIZON = -5			# degrees below horizon to be effectively dark
FULL_HEIGHT = 15			# height above horizon to presume full solar impact

class Orientation(cyin.Device):
	""" An orientation in space (a "facing").

		This object has state indicating the direction TO the Sun for someone
		facing this direction. It pays no attention to occlusion or obstacles.
	"""
	facing = cyin.PluginProperty(type=int, check=[check_range(min=0, max=360)])

	azimuth = cyin.DeviceState(type=float, format="\xb0")
	height = cyin.DeviceState(type=float, format="\xb0")
	index = cyin.DeviceState(type=int)

	_refresh_timer = None

	def start(self):
		self.set_display_address(astro.s_bearing(self.facing))
		if cyin.plugin.active:			# runtime start
			cyin.plugin.updateSun()

	def _update(self, sun):
		(A, h) = sun		# (Azimuth to true S, angular height)

		#
		# A is south-relative (0 = due South, -90 = due East, +145 = Northwest)
		#
		az = A - self.facing + 180		# north-by-north delta 
		az = (az + 180) % 360 - 180		# normalize to [-180, +180]

		# straight angles
		self.azimuth = round(az, 2)		# sun azimuth relative to facing
		self.height = round(h, 2)		# sun height over horizontal

		# judgment calls (rudimentary)
		if h < 0 or abs(az) > 90:		# sun not shining on this surface
			self.index = 0
		else:
			az_index = 100 - abs(az) * 100.0 / 90	# azimuth scale [0..100] <-> [90..0]
			h_index = h * 100.0 / FULL_HEIGHT	# height scale [0..100] <-> [0..FULL_HEIGHT]
			self.index = min(az_index, h_index)


#
# Actions
#
class Poll(cyin.DeviceAction):
	pass


#
# Events
#
class Precipitation(cyin.Event):
	location = cyin.PluginProperty(type=cyin.device)
	threshold = cyin.PluginProperty(type=int, check=[check_int(min=10,max=100)])

	def matches(self, location):
		if self.location:
			if self.location != location:
				return False
		return True


#
# The plugin.
#
SUN_REFRESH = 1 * 60	# every minute
#SUN_REFRESH = 1		# debug (every second)

class Plugin(cyin.asynplugin.Plugin):

	apikey = cyin.PluginPreference(type=str, required=False)

	def startup(self):
		cyin.asynplugin.Plugin.startup(self)
		self.setLocation()
		self._solar_refresh = self.schedule(self.updateSun)

	# update location on wakeup, just in case
	def wakeup(self):
		super(Plugin, self).wakeup()
		self.setLocation()
		self.updateSun()

	def setLocation(self):
		# set sun-tracking Location for "here"
		self._sunLoc = astro.SunLocation(*indigo.server.getLatitudeAndLongitude())
#		debug("location is", self._sunLoc)

	def updateSun(self, ctx=None):
		if ctx:
			ctx.reschedule(after=SUN_REFRESH)
		# else just do an update pass and leave the timer running
		sun = None
		for orient in Orientation.all():
			if sun is None:	# lazy
				sun = astro.sun_position(time.time(), self._sunLoc)
#				debug("sun is at", sun)
			orient._update(sun)
