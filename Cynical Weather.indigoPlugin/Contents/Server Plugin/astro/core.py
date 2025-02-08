#
# Astronomical support services - core support
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


#
# "Bare" geographic locations.
# (Actually, those work on any vaguely round planet.)
#
class Location(object):
	""" Hold a terrestrial position (latitude, longitude), West negative. """
	def __init__(self, lat, lon=None):
		if lon is None:		# from string: lat,lon
			(lat, _, lon) = lat.partition(',')
		self.lat = lat
		self.lon = lon

	@property
	def lat_lon(self):
		return (self.lat, self.lon)

	def __repr__(self):
		return "<%g,%g>" % (self.lat, self.lon)


#
# Convert latitudes, longitudes, bearings, etc. to human-readable format.
#
def s_latitude(lat):
	return u"%d\xb0%s" % (round(abs(lat)), "N" if lat >= 0 else "S")

def s_longitude(lon):
	lon = (round(lon) + 180) % 360 - 180	# normalize to [-180, +180)
	return u"%d\xb0%s" % (abs(lon), "E" if lon >= 0 else "W")

def s_location(lat, lon):
	""" Convert lat/lon degrees to human-readable short form. """
	return u"%s %s" % (s_latitude(lat), s_longitude(lon))


BEARINGS = {
	0:		"N",
	45:		"NE",
	90:		"E",
	135:	"SE",
	180:	"S",
	225:	"SW",
	270: 	"W",
	315:	"NW",
}

def s_bearing(azimuth):
	azimuth = round(azimuth) % 360	# [0, 360)
	s = BEARINGS.get(azimuth)
	if s:
		return s
	return u"%d\xb0" % azimuth
