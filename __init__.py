#!/usr/bin/python

from cortex.app import CortexFlask

# initalise cortex Flask application
app = CortexFlask(__name__)

# load user lib because some decorators are defined there
import cortex.lib.user

# load cortex modules so the decorators are processed
import cortex.errors
import cortex.admin
import cortex.views
import cortex.vmware
import cortex.systems
import cortex.puppet
import cortex.api
import cortex.register
import cortex.user

# load workflows - they have to be done here after app is created
app.load_workflows()
