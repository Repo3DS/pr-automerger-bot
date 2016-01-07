#!/usr/bin/env python3

# The HTTP server for recieving hooks
from http.server import BaseHTTPRequestHandler,HTTPServer
import socketserver
import json
from github import Github
import base64

import settings

def do_verify_commit(commit, permissions):
	# TODO Only supports one level deep validation at the moment
	for ghfile in commit.files:
		passed = False
		head = ghfile.filename.split('/', 1)[0]
		for pathperm in permissions:
			if head == pathperm['path']:
				# We're checking the right path! They need to pass this check, or they fail! FAIL I SAY
				for user in pathperm['users']:
					if user == "$everyone$":
						passed = True
						break
					if user == commit.committer.login:
						# User matched to the correct person, they have permissions!
						passed = True
						break
				break
		if not passed:
			# If we get here, the file didn't validate correclty :(
			return False
	
	# To get here means every file must have validated!
	return True
				

def do_magic_stuff(magic_json):
	repo = g.get_repo(magic_json['repository']['id'])

	""" Parse the permissions.txt (once per pull request) """
	# TODO Use the correct ref when fetching permissions.json
	# why is this base64 idek
	permissions = json.loads(base64.b64decode(repo.get_file_contents('permissions.json').content).decode('utf-8'))
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

	""" verify the validity of each commit """
	for commit in pull.get_commits():
		if not do_verify_commit(commit, permissions):
			pull.create_issue_comment("Sorry, it looks like you don't have permission to make this change, so I can't automatically merge it. Perhaps you didn't even want me to! Lets hope so, anyway, because I'm not going to.")
			print("Not merging request!")
			return False

	print("Merging request!")
	pull.create_issue_comment("Looks like you have permission to make this change, so I've automatically merged it for you. If this was a mistake, well, tough luck at this point, but I'm sure we'll let you revert it yourself at a later date.")
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


