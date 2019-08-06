from cortex import app
import cortex.corpus.rubrik 

# This class is just a thin wrapper around the corpus Rubrik object, that pulls 
# config from our global app object rather than needing a TaskHelper object
class Rubrik(cortex.corpus.rubrik.Rubrik):
	def __init__(self, helper=None):
		super().__init__(app)
