
class InvalidPermissionException(Exception):
	message = "Permission Denied: You do not have permission to access that page or perform that action."
	status_code = 403

	def __str__(self):
		return self.message

class UnauthorizedException(Exception):
	message = "Unauthorized: You are unauthorized to access that resource."
	status_code = 401

	def __str__(self):
		return self.message

class NoResultsFoundException(Exception):
	message = "Not Found: No results were found."
	status_code = 404

	def __str__(self):
		return self.message

class BadRequestException(Exception):
	message = "Bad Request: The request format is not correct."
	status_code = 400
	
	def __str__(self):
		return self.message
