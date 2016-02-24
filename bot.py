#!/usr/bin/env python3

# The HTTP server for recieving hooks
from http.server import BaseHTTPRequestHandler, HTTPServer
from github import Github
from os import path
from PIL import Image
import urllib.request, socketserver, base64, json, yaml
import settings, brewman


def do_verify_commit(commit, permissions):
	errorlist = []
	configs_checked = 0
	is_org_member = any(org.login != "Repo3ds" for org in commit.committer.get_orgs())

	for ghfile in commit.files:
		ghdir = path.dirname(ghfile.filename)
		ghbase = path.basename(ghfile.filename)

		# Members of the Repo3ds org have permission to modify everything
		passed = is_org_member
		for pathname, users in permissions.items():
			# Because trailing slash is optional in permissions file
			if ghdir == path.dirname(pathname+'/'):
				if "$everyone$" in users or commit.committer.login in users:
					passed = True
					break
		if not passed:
			errorlist += ["[{}]({}) does not have permission to edit file [{}]({})".format(commit.committer.login, commit.committer.html_url, ghfile.filename, ghfile.blob_url)]

		# Validate the config file that was changed
		if ghbase == "config.yml":
			# Don't check more than one config that they don't have permission to edit
			if configs_checked < 1 or passed:
				configs_checked += 1
				tmpfile, headers = urllib.request.urlretrieve(ghfile.raw_url)
				try:
					with open(tmpfile) as f:
						config = yaml.load(f)
						app = brewman.BrewConfig(config, path.basename(ghdir))
						errorlist += app.validate()
				except yaml.YAMLError as e:
					errorlist += ["Error parsing configuration file."]
		
		# Make sure icon.png is a valid 48x48 PNG file
		elif ghbase == "icon.png":
			tmpfile, headers = urllib.request.urlretrieve(ghfile.raw_url)
			try:
				icon = Image.open(tmpfile)
				if icon.format != 'PNG':
					errorlist += ["[icon.png]({}) is not a valid PNG.".format(ghfile.blob_url)]
				if icon.size != (48, 48):
					errorlist += ["[icon.png]({}) dimensions need to be 48x48".format(ghfile.blob_url)]
			except Exception:
				errorlist += ["[icon.png]({}) is not a valid image.".format(ghfile.blob_url)]

		# If you have permission to the directory, but not file
		elif passed and not is_org_member:
			errorlist += ["[{}]({}) does not have permission to edit file [{}]({})".format(commit.committer.login, commit.committer.html_url, ghfile.filename, ghfile.blob_url)]

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
		print("PR has changed, not merging")
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
