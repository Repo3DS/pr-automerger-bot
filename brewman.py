#!/usr/bin/env python3

import os, sys, getopt, yaml, hashlib, urllib.request, tempfile
import zipfile, tarfile, rarfile, re
from PIL import Image


class BrewConfig:
	def __init__(self, config, dir):
		self.config = config
		self.dir = dir

	# Make sure all required fields exist
	def check_required(self):
		errorlist = []
		required = ["title","author","version","description","file","filesize","file-md5"]
		for key in required:
			if not key in self.config:
				errorlist += ["Key `{}` required but not found in configuration file.".format(key)]
		return errorlist

	# Download the file and make sure everything is proper
	def check_file(self):
		errorlist = []
		if all (key in self.config for key in ("file","filesize","file-md5")):
			tmpfile = tempfile.NamedTemporaryFile(delete = False)
			md5sum = hashlib.md5()
			bytes = 0

			with urllib.request.urlopen(self.config["file"]) as f:
				for chunk in iter(lambda: f.read(4096), b""):
					bytes += len(chunk)
					tmpfile.write(chunk)
					md5sum.update(chunk)
					if bytes > 100 * 1024 * 1024:
						errorlist += ["File provided is too large. (100MB limit)"]
						break
			tmpfile.close()

			# If everything downloaded fine
			if not errorlist:
				filelist = []
				if not md5sum.hexdigest() == self.config["file-md5"]:
					errorlist += ["Hash provided by `file-md5` does not match file checksum."]
				if not bytes == self.config["filesize"]:
					errorlist += ["Value for `filesize` is incorrect."]
				
				# TODO: check for 7z format too, the 3ds app already supports it
				if zipfile.is_zipfile(tmpfile.name):
					with zipfile.ZipFile(tmpfile.name) as archive:
						filelist = archive.namelist()
				elif tarfile.is_tarfile(tmpfile.name):
					with tarfile.open(tmpfile.name) as archive:
						filelist = archive.getnames()
				elif rarfile.is_rarfile(tmpfile.name):
					with rarfile.RarFile(tmpfile.name) as archive:
						filelist = [x.replace('\\','/') for x in archive.namelist()]
				else:
					errorlist += ["`file` is not a recognized archive. Supported types: *.rar *.zip *.tar.(bz2|gz|xz}"]

				# Check if files are in permitted locations
				for filename in filelist:
					base = os.path.dirname(filename)
					# Zipfile returns directories (e.g. 3ds/) for some stupid reason
					if not filename == '3ds/' and not base.startswith("3ds/"+self.dir):
						errorlist += ["Archive file `{}` is not in a permitted location.".format(filename)]

				# Check for expected 3dsx file
				filename = '3ds/' + self.dir + '/' + self.dir + '.3dsx'
				if not filename in filelist:
					errorlist += ["Expected file not found: `{}`".format(filename)]

			os.remove(tmpfile.name)

		return errorlist

	# Validates everything, returning an empty error list if validation succeeds
	def validate(self):
		errorlist = self.check_required()
		fields = ["title","author","version","description","long-description","n3ds-only","file","filesize","file-md5","screenshots","install-message"]

		for key, val in self.config.items():
			if key == "title":
				if len(val) > 25:
					errorlist += ["Value for `title` is too long. (25 char limit)"]
			elif key == "file":
				if not is_url(val):
					errorlist += ["The URL provided by `file` cannot be opened."]
			elif key == "filesize":
				if type(val) is not int:
					errorlist += ["Improper value for `filesize`. Must be a number."]
				elif val > 100 * 1024 * 1024:
					errorlist += ["Value for `filesize` is too large. (100MB limit)"]
			elif key == "screenshots":
				if isinstance(val, list):
					if len(val) > 5:
						errorlist += ["Screenshot limit exceeded. Only 5 screenshot links currently permitted."]
					for imageurl in val:
						if re.match('https?://i.imgur.com/', imageurl):
							try:
								tmpfile, headers = urllib.request.urlretrieve(imageurl)
							except Exception:
								errorlist += ["Screenshot URL does not return a valid image: {}".format(imageurl)]
							try:
								image = Image.open(tmpfile)
								if not image.format in ['PNG','JPEG']:
									errorlist += ["Screenshot URL returns a {} image, but only PNG and JPEG are supported: {}".format(image.format, imageurl)]
								if image.size != (400, 480):
									errorlist += ["Screenshot dimensions must be 400x480: {}".format(imageurl)]
							except Exception:
								errorlist += ["Screenshot URL does not return a valid image: {}".format(imageurl)]
						else:
							errorlist += ["Screenshot URL is not valid, only [Imgur](https://imgur.com/) currently supported: {}".format(imageurl)]
				else:
					errorlist += ["Value for `screenshots` must be a list."]
			elif key not in fields:
				errorlist += ["Unknown field `{}` in configuration file.".format(key)]
		
		if not errorlist:
			errorlist = self.check_file()

		return errorlist


def is_url(url):
		try:
			urllib.request.urlopen(url)
			return True
		except Exception:
			return False

def print_help():
	print('brewman.py -i <inputfile>')

def main(argv):
	inputfile = ''
	dirname = ''
	try:
		opts, args = getopt.getopt(argv,"hi:d:",["help","file=","dir="])
	except getopt.GetoptError:
		print_help()
		sys.exit(2)
	for opt, arg in opts:
		if opt in ("-h", "--help"):
			print_help()
			sys.exit()
		elif opt in ("-i", "--file"):
			inputfile = arg
		elif opt in ("-d", "--dir"):
			dirname = arg

	if inputfile and dirname:
		try:
			with open(inputfile) as f:
				config = yaml.load(f)
				app = BrewConfig(config, dirname)
				errorlist = app.validate()
				if errorlist:
					for error in errorlist:
						print(error)
				else:
					print("Validated successfully")
		except yaml.YAMLError as e:
			print("Error in configuration file:", e)
	else:
		print_help()
		

if __name__ == "__main__":
	main(sys.argv[1:])