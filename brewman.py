#!/usr/bin/env python3

import os, sys, getopt, yaml, hashlib, urllib.request, tempfile
import zipfile, tarfile


class BrewConfig:
	def __init__(self, config):
		self.config = config

	# Make sure all required fields exist
	def check_required(self):
		errorlist = []
		required = ["title","dir","author","version","description","file","filesize","file-md5"]
		for key in required:
			if not key in self.config:
				errorlist += ["Key `{}` required but not found in configuration file.".format(key)]
		return errorlist

	# Download the file and make sure everything is proper
	def check_file(self):
		errorlist = []
		if all (key in self.config for key in ("dir","file","filesize","file-md5")):
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
				
				if zipfile.is_zipfile(tmpfile.name):
					with zipfile.ZipFile(tmpfile.name) as archive:
						filelist = archive.namelist()
				elif tarfile.is_tarfile(tmpfile.name):
					with tarfile.open(tmpfile.name) as archive:
						filelist = archive.getnames()
				else:
					errorlist += ["`file` is not a recognized archive. Supported types: *.zip *.tar.bz2 *.tar.xz"]

				# Check if files are in permitted locations
				for filename in filelist:
					base = os.path.dirname(filename)
					# Zipfile returns directories (e.g. 3ds/) for some stupid reason
					if not filename == '3ds/' and not base == "3ds/{}".format(self.config["dir"]):
						errorlist += ["Archive file `{}` is not in a permitted location.".format(filename)]

			os.remove(tmpfile.name)

		return errorlist

	# Validates everything, returning an empty error list if validation succeeds
	def validate(self):
		errorlist = self.check_required()
		for key, val in self.config.items():
			if key == "title":
				if len(val) > 25:
					errorlist += ["Value for `title` is too long. (25 char limit)"]
			elif key == "file":
				try:
					urllib.request.urlopen(val)
				except Exception:
					errorlist += ["The URL provided by `file` cannot be opened."]
			elif key == "filesize":
				if type(val) is not int:
					errorlist += ["Improper value for `filesize`. Must be a number."]
				elif val > 100 * 1024 * 1024:
					errorlist += ["Value for `filesize` is too large. (100MB limit)"]
		
		if not errorlist:
			errorlist = self.check_file()

		return errorlist


def print_help():
	print('brewman.py -i <inputfile>')

def main(argv):
	inputfile = ''
	try:
		opts, args = getopt.getopt(argv,"hi:",["help","file="])
	except getopt.GetoptError:
		print_help()
		sys.exit(2)
	for opt, arg in opts:
		if opt in ("-h", "--help"):
			print_help()
			sys.exit()
		elif opt in ("-i", "--file"):
			inputfile = arg

	if inputfile:
		try:
			with open(inputfile) as f:
				config = yaml.load(f)
				app = BrewConfig(config)
				errorlist = app.validate()
				if errorlist:
					for error in errorlist:
						print(error)
				else:
					print("Validated successfully")
		except yaml.YAMLError as e:
			print("Error in configuration file:", e)
		

if __name__ == "__main__":
	main(sys.argv[1:])