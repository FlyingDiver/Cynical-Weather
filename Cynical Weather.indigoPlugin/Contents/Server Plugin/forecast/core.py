#
# forecast.core - forecast basic infrastructure
#
# Copyright 2013-2016,2022-2023 Perry The Cynic. All rights reserved.
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
# This is currently using the (excellent) Visualcrossing.com service.
# See https://www.visualcrossing.com/resources/documentation/weather-api/timeline-weather-api.
#
import time
import datetime
import urllib.parse

import json

from astro import Location

import asyn
import asyn.http

DEBUG = None


#
# System parameters.
#
APIHOST = 'weather.visualcrossing.com'


#
# A "data point" in Visual Crossing parlance
#
class Point(object):

	def __init__(self, data, units):
		self.units = units
		def convert(name, type, default=None, source=None):
			source = source or name
			value = data.get(source) or default
			#if DEBUG: DEBUG(f"convert {source}->{name} from {data.get(source)} default {default} -> {type}({value})")
			setattr(self, name, None if value is None else type(value))
		convert("datetime",				str)
		convert("datetimeEpoch",		int)
		convert("summary",				str, "", source="description")
		convert("conditions",			str, "")
		convert("icon",					str, "unknown")
		convert("temp",					float)
		convert("tempmin",				float)
		convert("tempmax",				float)
		convert("feelslike",			float)
		convert("feelslikemin",			float)
		convert("feelslikemax",			float)
		convert("dew",					float)
		convert("humidity",				float)
		convert("pressure",				float)
		convert("visibility",			float)
		convert("cloudcover",			float)
		convert("windspeed",			float, 0)
		convert("windgust",				float, self.windspeed)
		convert("winddir",				float, 360)
		convert("precip",				float, 0)
		convert("precipprob",			float, 0)
		convert("uvindex",				float, 0)
		convert("solarradiation",		float, 0)
		convert("solarenergy",			float, 0)
		convert("moonphase",			float)
		convert("severerisk",			int, 0)

	def __repr__(self):
		return "<Forecast Point@{time.ctime(self.datetimeepoch)} T{self.temp} H{self.humidity}"


#
# A vector of data points
#
class List(list):

	def __init__(self, data, units):
		if data is None:
			self.min = self.max = None
		else:
			list.__init__(self, [Point(dp, units) for dp in data])
			times = [dp.datetimeEpoch for dp in self]
			self.min = min(times)
			self.max = max(times)


#
# A weather alert
#
class Alert(object):

	def __init__(self, data):
		if DEBUG: DEBUG("alert from:", data)
		self.id = data.get("id")
		self.headline = data.get("headline")
		self.description = data.get("description")
		self.onset = datetime.datetime.fromtimestamp(data.get("onsetEpoch"))
		self.ends = datetime.datetime.fromtimestamp(data.get("endsEpoch"))
		self.link = data.get("link")

	def __repr__(self):
		return f"Alert({self.id=} {self.headline=} {self.description=} {self.link=})"


#
# A full reading (reply) as delivered by the weather service
#
class Reading(object):

	def __init__(self, data, units):
		if DEBUG:
			with open("/tmp/weather-reading.json", "wb") as f:
				f.write(data)
		self.raw = data
		self.units = units
		s = json.loads(data)
		self.location = Location(s["latitude"], s["longitude"])
		self.alerts = [Alert(ad) for ad in s.get("alerts", [])]
		current = s.get("currentConditions")
		self.current = Point(current, self.units) if current else None
		dayData = s.get("days")
		if dayData:
			self.days = List(dayData, self.units)
		hourData = dayData[0].get("hours")
		if hourData:
			self.hours = List(hourData, self.units)

	def getPoint(self, distance, units='days'):
		if DEBUG: DEBUG(f"getPoint {distance} {units} for {self}")
		if units == 'now' or units is None:
			return self.current
		if units == 'days':
			base = self.days
		elif units == 'hours':
			base = self.hours
		else:
			return None
		if distance >= len(base):
			return None
		if DEBUG: DEBUG("get", distance, units, " => ", base[distance])
		return base[distance]
	
	def __repr__(self):
		return "<Reading%s current%s>" % (self.location, self.current)


#
# A communications channel to the weather service.
#
class Forecast(asyn.Callable):
	""" Interface to the weather service.

		This class contacts a fixed service vending Visual Crossing data and
		obtains one "reading", a present-time full data set at a given location.
	"""
	def __init__(self, control, callout=None):
		asyn.Callable.__init__(self, callout=callout)
		self.control = control
		self.apikey = None
		self.location = None
		self.user_agent = None
		self.units = 'us'

	def poll(self, callout):
		""" Explicitly get data from the weather service, using preset parameters. """
		assert self.apikey is not None
		def cb(ctx, *args):
			if ctx.error:
				callout(ctx)
				req.close()
			elif ctx.state == 'body':
				if req.n_status == '200':
					callout(asyn.Context('reading'), Reading(args[0], self.units))
				else:
					callout(asyn.Context('error'), req)
		query = dict(
			units=self.units
		)
		req = self._request("forecast", callout=cb, query=query)


	#
	# Web interface primitives
	#
	def _request(self, req, callout=None, action='GET', query=None):
		""" Send a web request to the weather server. """
		query = {
			"unitGroup": self.units,
			"key": self.apikey
		}
		request = asyn.http.request(self.control, callout=callout, action=action, query=query)
		if self.user_agent:
			request.user_agent = self.user_agent + ' ' + request.user_agent
		request.open(self._weburl(req))
		return request

	def _weburl(self, op):
		return urllib.parse.urlunsplit(('https', APIHOST,
			f"/VisualCrossingWebServices/rest/services/timeline/{self.location.lat},{self.location.lon}",
			None, None))


#
# Regression test
#
if __name__ == "__main__":
	import getopt, sys

	def cb(ctx, arg = None):
		print("MAIN CALLOUT", ctx, arg)

	def dlog(*it):
		print(' '.join(map(str, it)))

	opts, args = getopt.getopt(sys.argv[1:], "H")
	for opt, value in opts:
		if opt == '-H':
			asyn.http.DEBUG = dlog
	control = asyn.Controller()
	forecast = Forecast(control, callout=cb)
	forecast.apikey = args[0]
	forecast.location = Location(85, 90)
	def rep(ctx, arg=None):
		if ctx.error:
			print("ERROR", ctx.error)
		elif ctx.state == 'error':
			print("HTTP", arg.n_status, arg.v_status)
		elif ctx.state == 'reading':
			print("Reading:", arg)
		else:
			print("UNEXPECTED", ctx, arg)
		control.close()
	forecast.poll(rep)
	control.run()
