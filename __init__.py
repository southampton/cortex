
from cortex.app import CortexFlask

# initalise cortex Flask application
app = CortexFlask(__name__)

# load user lib because some decorators are defined there
import cortex.lib.user

# load per-request functions (set via decorators)
import cortex.request

# load cortex views modules so the decorators are processed
import cortex.views.errors
import cortex.views.admin
import cortex.views.views
import cortex.views.vmware
import cortex.views.systems
import cortex.views.puppet
import cortex.views.api
import cortex.views.register
import cortex.views.user
import cortex.views.perms
import cortex.views.favourites
import cortex.views.certificates

# load blueprints
from cortex.api import api_blueprint
app.register_blueprint(api_blueprint)
from cortex.views.tenable import tenable
app.register_blueprint(tenable)

# load workflows - they have to be done here after app is created
app.load_workflows()
