import cortex.corpus.rubrik
from cortex import app


# This class is just a thin wrapper around the corpus Rubrik object, that pulls
# config from our global app object rather than needing a TaskHelper object
class Rubrik(cortex.corpus.rubrik.Rubrik):
	def __init__(self, helper=None):
		super().__init__(app)

RubrikVMNotFound = cortex.corpus.rubrik.RubrikVMNotFound
RubrikVCenterNotFound = cortex.corpus.rubrik.RubrikVCenterNotFound
