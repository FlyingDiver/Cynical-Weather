from __future__ import print_function
from __future__ import absolute_import
#
# suntrack - celestial position calculations
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
# Formulas: http://aa.quae.nl/en/reken/zonpositie.html
# Regression: http://www.suncalc.net
# Thanks a bunch!
#
import time

from astro import core

DEBUG = None


#
# Characterize the Earth.
# Should we ever move to Mars, those parameter could be swapped out to match...
#
class Planet(object):
	def __init__(self, name, **kwargs):
		self.name = name
		for attr in kwargs:
			setattr(self, attr, kwargs[attr])

	def __repr__(self):
		return self.name


EARTH = Planet("Earth",
	A2 = -2.4680, A4 = +0.0530, A6 = -0.0014,
	Cn = [1.9148, 0.0200, 0.0003, 0, 0, 0],
	D1 = 22.8008, D3 = +0.5999, D5 = +0.0493,
	M0 = 357.5291, M1 = 0.98560028,
	TH0 = 280.1600, TH1 = 360.9856235,
	EL = 102.9372,					# ecliptic longitude
	ET = 23.45,						# ecliptic tilt
)


#
# Geographic locations
#
class SunLocation(core.Location):
	""" Hold a terrestrial position (latitude, longitude), West positive. """
	def __init__(self, lat, lon=None, planet=EARTH):
		super(SunLocation, self).__init__(lat=lat, lon=lon)
		self.planet = planet

		# pre-calculate
		self.lat_sin = sin(lat)
		self.lat_cos = cos(lat)
		self.lon_sin = sin(lon)
		self.lon_cos = cos(lon)

	def __repr__(self):
		return "<%g,%g@%s>" % (self.lat, self.lon, self.planet)


#
# Needed trigonometry (angles are degrees)
#
import math
def sin(s): return math.sin(math.radians(s))
def cos(s): return math.cos(math.radians(s))
def tan(s): return math.tan(math.radians(s))
def arctan(s, t): return math.degrees(math.atan2(s, t))
def arcsin(s): return math.degrees(math.asin(s))

J2000 = 2451545					# Year 2000 Julian epoch


#
# Calculate the solar position as (Azimuth, Height angle)
#
# This is a convenient approximation. But then, this is physics.
#
def sun_position(unixtime, location):
	""" Calculate the horizon coordinates of the Sun at a given time and location. """
	p = location.planet

	#
	# Variable names are as used in the source material.
	#
	J = unixtime / 86400.0 + 2440587.5			# convert UNIX to Julian time

	M = p.M0 + p.M1 * (J - J2000)				# mean orbital anomaly
	C = sum([p.Cn[i] * sin((i+1) * M) for i in range(0, len(p.Cn))])	# eq. of center
	l_sun = M + p.EL + C + 180					# ecliptic longitude
	if DEBUG: DEBUG("J", J, "M", M % 360, "C", C, "l_sun", l_sun % 360)

	# equatorial coordinates of the Sun
	alpha_sun = l_sun + p.A2 * sin(2 * l_sun) + p.A4 * sin(4 * l_sun) + p.A6 * sin(6 * l_sun)
	delta_sun = p.D1 * sin(l_sun) + p.D3 * sin(l_sun)**3 + p.D5 * sin(l_sun)**5
	TH = p.TH0 + p.TH1 * (J - J2000) + location.lon		# sidereal time
	if DEBUG: DEBUG("sun alpha/delta", alpha_sun % 360, delta_sun, "siderial time", TH % 360)

	#
	# Convert to observer coordinates
	#
	H = (TH - alpha_sun) % 360
	A = arctan(sin(H), cos(H) * location.lat_sin - tan(delta_sun) * location.lat_cos)
	h = arcsin(location.lat_sin * sin(delta_sun) + location.lat_cos * cos(delta_sun) * cos(H))
	if DEBUG: DEBUG("H", H, "A/h", A, h)

	# here you are!
	return (A, h)		# ascension, height


#
# Test
#
if __name__ == "__main__":
	pos = SunLocation(lat=37.265, lon=-121.96)		# where I live

	import sys
	if len(sys.argv) == 1:						# rudimentary regresson test
		sdate = 'Sat Apr  1 4:00:00 UTC 2004'
		pos = SunLocation(lat=52, lon=5)
	else:
		sdate = ' '.join(sys.argv[1:])			# date with spaces from command line
	try:
		ts = int(sdate)
	except ValueError:
		ts = time.mktime(time.strptime(sdate, "%a %b %d %H:%M:%S %Z %Y"))

	(A, h) = sun_position(ts, pos)

	if len(sys.argv) == 1:
		if abs(A - 5.1302) > 0.001 or abs(h - 42.6542) > 0.001:
			print("BAD COMPARE!")
		else:
			print("Regression OK.")
	else:
		print("Ascension", A, "height", h)
