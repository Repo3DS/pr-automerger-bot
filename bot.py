#!/usr/bin/env python3

# The HTTP server for recieving hooks
from http.server import BaseHTTPRequestHandler, HTTPServer
from github import Github
from os import path
import urllib.request, socketserver, base64, json, yaml, struct, imghdr
import settings, brewman


def do_verify_commit(commit, permissions):
	errorlist = []

	for ghfile in commit.files:
		ghdir = path.dirname(ghfile.filename)
		ghbase = path.basename(ghfile.filename)

		passed = False
		for pathname, users in permissions.items():
			# Because trailing slash is optional in permissions file
			if ghdir == path.dirname(pathname+'/'):
				if "$everyone$" in users or commit.committer.login in users:
					passed = True
					break
		if not passed:
			errorlist += ["You do not have permission to edit file [{}]({})".format(ghfile.filename, ghfile.blob_url)]

		# Validate the config file that was changed
		if ghbase == "config.yml":
			tmpfile, headers = urllib.request.urlretrieve(ghfile.raw_url)
			try:
				with open(tmpfile) as f:
					config = yaml.load(f)
					app = brewman.BrewConfig(config)
					errors = app.validate()
					if not errors:
						print("Validated successfully")
					else:
						errorlist += errors
			except yaml.YAMLError as e:
				errorlist += ["Error parsing configuration file."]
		
		# Make sure icon.png is a valid 48x48 PNG file
		elif ghbase == "icon.png":
			tmpfile, headers = urllib.request.urlretrieve(ghfile.raw_url)
			with open(tmpfile, 'rb') as f:
				head = f.read(24)
				if len(head) == 24:
					check = struct.unpack('>i', head[4:8])[0]
				if len(head) != 24 or imghdr.what(tmpfile) != 'png' or check != 0x0d0a1a0a:
					errorlist += ["Icon file is not a valid PNG file."]
				else:
					width, height = struct.unpack('>ii', head[16:24])
					if width != 48 or height != 48:
						errorlist += ["[icon.png]({}) dimensions are {}x{} instead of the required 48x48".format(ghfile.blob_url, width, height)]
		
		# Must be checked last
		elif passed:
			errorlist += ["You do not have permission to edit file [{}]({})".format(ghfile.filename, ghfile.blob_url)]

	return errorlist
				

def do_magic_stuff(magic_json):
	repo = g.get_repo(magic_json['repository']['id'])

	""" Parse the permissions.txt (once per pull request) """
	permissions = yaml.load(base64.b64decode(repo.get_file_contents('permissions.yml').content).decode('utf-8'))
	pull = repo.get_pull(magic_json['number'])

	# TODO Verify whether we've commented on this repo before
	# For now, the lazy way is kind of "is this merged?"
	if pull.merged:
		print("Not merging -- it's already been merged")
		return False
	
	# Another sanity check is whether it's mergable in the first place
	if not pull.mergeable:
		print("Not merging -- not mergeable")
		return False

	""" verify the validity of the commit """
	if pull.commits > 1:
		pull.create_issue_comment("This PR cannot be reviewed/merged properly until the {} commits are squashed into 1.".format(pull.commits))
		return False
	commit = pull.get_commits()[0]
	errors = do_verify_commit(commit, permissions)

	# Check the PR again to make sure nothing changed while it was being verified
	pull = repo.get_pull(magic_json['number'])
	if pull.commits > 1 or commit.sha != pull.get_commits()[0].sha:
		do_magic_stuff(magic_json)
		return False

	# If errors are returned, make an issue comment about all of them
	if errors:
		comment = "This pull request cannot be merged for the following reasons:\n"
		for error in errors:
			comment += "- {}\n".format(error)
		pull.create_issue_comment(comment)
		print("Not merging request!")
		return False

	# If no errors returned, epic success!
	print("Merging request!")
	pull.create_issue_comment("Everything looks good to me, so I've automatically merged it for you. If this was a mistake, well, tough luck at this point, but I'm sure we'll let you revert it yourself at a later date.")
	pull.merge()
	return True

class MyHandler(BaseHTTPRequestHandler):
	def do_POST(self):
		self.send_response(200);
		self.send_header("Content-type", "application/json")
		self.end_headers()

		""" If it's a Pull Request, lets do our business! """
		if self.headers["X-GitHub-Event"] == "pull_request":
			""" We should verify the secret, but it makes little difference at this point """
			content_len = int(self.headers['content-length'])
			post_body = self.rfile.read(content_len)
			# print(post_body)
			do_magic_stuff(json.loads(post_body.decode("utf-8")))

		""" No matter what, consider it a success """
		self.wfile.write(bytes('{"success": true}', 'utf-8'))
		return

if __name__ == '__main__':
	global g
	""" Check our Github API connection """
	g = Github(settings.GHUSER, settings.GHPASS)

	""" Start our hook listen and loop forever """
	httpd = HTTPServer(("", settings.PORT), MyHandler)
	print("Server Starts - %s" % (settings.PORT))
	try:
		httpd.serve_forever()
	except KeyboardInterrupt:
		pass
	httpd.server_close()
	print("done")
