"""
    flask.ext.restless.manager
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    Provides :class:`flask.ext.restless.manager.APIManager`, the class which
    users of Flask-Restless must instantiate to create ReSTful APIs for their
    database models.

    :copyright:2011 by Lincoln de Sousa <lincoln@comum.org>
    :copyright:2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""

from flask import Blueprint
from sqlalchemy.orm import scoped_session

from .views import API
from .views import FunctionAPI
from .views import _get_onetomany_relations
from .views import _related_collection

#: The set of methods which are allowed by default when creating an API
READONLY_METHODS = frozenset(('GET', ))


class IllegalArgumentError(Exception):
    """This exception is raised when a calling function has provided illegal
    arguments to a function or method.

    """
    pass


class APIManager(object):
    """Provides a method for creating a public ReSTful JSOn API with respect to
    a given :class:`~flask.Flask` application object.

    The :class:`~flask.Flask` object can be specified in the constructor, or
    after instantiation time by calling the :meth:`init_app` method. In any
    case, the application object must be specified before calling the
    :meth:`create_api` method.

    """

    #: The format of the name of the API view for a given model.
    #:
    #: This format string expects the name of a model to be provided when
    #: formatting.
    APINAME_FORMAT = '%sapi'

    #: The format of the name of the blueprint containing the API view for a
    #: given model.
    #:
    #: This format string expects the following to be provided when formatting:
    #:
    #: 1. name of the API view of a specific model
    #: 2. a number representing the number of times a blueprint with that name
    #:    has been registered.
    BLUEPRINTNAME_FORMAT = '%s%s'

    def __init__(self, app=None, session=None, flask_sqlalchemy_db=None):
        """Stores the specified :class:`flask.Flask` application object on
        which API endpoints will be registered.

        If `app` is ``None`` or one of `session` and `flask_sqlalchemy_db_` is
        ``None``, the user must call the :meth:`init_app` method before calling
        the :meth:`create_api` method.

        `app` is the :class:`flask.Flask` object containing the user's Flask
        application.

        `session` is the :class:`session.orm.session.Session` object in which
        changes to the database will be made. It may also be a
        :class:`session.orm.session.Session` class, in which case a new
        :class:`sqlalchemy.orm.scoped_session` will be created from it.

        `flask_sqlalchemy_db` is the :class:`flask.ext.sqlalchemy.SQLAlchemy`
        object with which `app` has been registered and which contains the
        database models for which API endpoints will be created.

        If `flask_sqlalchemy_db` is not ``None``, `session` will be ignored.

        For example, to use this class with models defined in pure SQLAlchemy::

            from flask import Flask
            from flask.ext.restless import APIManager
            from sqlalchemy import create_engine
            from sqlalchemy.orm.session import sessionmaker

            engine = create_engine('sqlite:////tmp/mydb.sqlite')
            Session = sessionmaker(bind=engine)
            mysession = Session()
            app = Flask(__name__)
            apimanager = APIManager(app, session=mysession)

        and with models defined with Flask-SQLAlchemy::

            from flask import Flask
            from flask.ext.restless import APIManager
            from flask.ext.sqlalchemy import SQLAlchemy

            app = Flask(__name__)
            db = SQLALchemy(app)
            apimanager = APIManager(app, flask_sqlalchemy_db=db)

        """
        self.init_app(app, session, flask_sqlalchemy_db)

    def _next_blueprint_name(self, basename):
        """Returns the next name for a blueprint with the specified base name.

        This method returns a string of the form ``'{}{}'.format(basename,
        number)``, where ``number`` is the next non-negative integer not
        already used in the name of an existing blueprint.

        For example, if `basename` is ``'personapi'`` and blueprints already
        exist with names ``'personapi0'``, ``'personapi1'``, and
        ``'personapi2'``, then this function would return ``'personapi3'``. We
        expect that code which calls this function will subsequently register a
        blueprint with that name, but that is not necessary.

        """
        # blueprints is a dict whose keys are the names of the blueprints
        blueprints = self.app.blueprints
        existing = [name for name in blueprints if name.startswith(basename)]
        # if this is the first one...
        if not existing:
            next_number = 0
        else:
            # for brevity
            b = basename
            existing_numbers = [int(n.partition(b)[-1]) for n in existing]
            next_number = max(existing_numbers) + 1
        return APIManager.BLUEPRINTNAME_FORMAT % (basename, next_number)

    def init_app(self, app, session=None, flask_sqlalchemy_db=None):
        """Stores the specified :class:`flask.Flask` application object on
        which API endpoints will be registered and the
        :class:`sqlalchemy.orm.session.Session` object in which all database
        changes will be made.

        `session` is the :class:`session.orm.session.Session` object in which
        changes to the database will be made.

        `flask_sqlalchemy_db` is the :class:`flask.ext.sqlalchemy.SQLAlchemy`
        object with which `app` has been registered and which contains the
        database models for which API endpoints will be created.

        If `flask_sqlalchemy_db` is not ``None``, `session` will be ignored.

        This is for use in the situation in which this class must be
        instantiated before the :class:`~flask.Flask` application has been
        created.

        To use this method with pure SQLAlchemy, for example::

            from flask import Flask
            from flask.ext.restless import APIManager
            from sqlalchemy import create_engine
            from sqlalchemy.orm.session import sessionmaker

            apimanager = APIManager()

            # later...

            engine = create_engine('sqlite:////tmp/mydb.sqlite')
            Session = sessionmaker(bind=engine)
            mysession = Session()
            app = Flask(__name__)
            apimanager.init_app(app, session=mysession)

        and with models defined with Flask-SQLAlchemy::

            from flask import Flask
            from flask.ext.restless import APIManager
            from flask.ext.sqlalchemy import SQLAlchemy

            apimanager = APIManager()

            # later...

            app = Flask(__name__)
            db = SQLALchemy(app)
            apimanager.init_app(app, flask_sqlalchemy_db=db)

        """
        self.app = app
        self.session = session or flask_sqlalchemy_db.session
        if isinstance(self.session, type):
            self.session = scoped_session(self.session)

    def create_api_blueprint(self, model, methods=READONLY_METHODS,
                             url_prefix='/api', collection_name=None,
                             allow_patch_many=False, allow_functions=False,
                             authentication_required_for=None,
                             authentication_function=None,
                             include_columns=None,
                             patch_columns=None,
                             validation_exceptions=None,
                             results_per_page=10,
                             post_form_preprocessor=None,
                             post_form_postprocessor=None,
                             patch_form_preprocessor=None,
                             patch_form_postprocessor=None,
                             delete_form_preprocessor=None,
                             delete_form_postprocessor=None,
                             get_result_postprocessor=None,
                             get_request_preprocessor=None):
        """Creates an returns a ReSTful API interface as a blueprint, but does
        not register it on any :class:`flask.Flask` application.

        The endpoints for the API for ``model`` will be available at
        ``<url_prefix>/<collection_name>``. If `collection_name` is ``None``,
        the lowercase name of the provided model class will be used instead, as
        accessed by ``model.__name__``. (If any black magic was performed on
        ``model.__name__``, this will be reflected in the endpoint URL.)

        This function must be called at most once for each model for which you
        wish to create a ReSTful API. Its behavior (for now) is undefined if
        called more than once.

        This function returns the :class:`flask.Blueprint` object which handles
        the endpoints for the model. The returned :class:`~flask.Blueprint` has
        already been registered with the :class:`~flask.Flask` application
        object specified in the constructor of this class, so you do *not* need
        to register it yourself.

        `model` is the :class:`flask.ext.restless.Entity` class for which a
        ReSTful interface will be created. Note this must be a class, not an
        instance of a class.

        `methods` specify the HTTP methods which will be made available on the
        ReSTful API for the specified model, subject to the following caveats:

        * If :http:method:`get` is in this list, the API will allow getting a
          single instance of the model, getting all instances of the model, and
          searching the model using search parameters.
        * If :http:method:`patch` is in this list, the API will allow updating
          a single instance of the model, updating all instances of the model,
          and updating a subset of all instances of the model specified using
          search parameters.
        * If :http:method:`delete` is in this list, the API will allow deletion
          of a single instance of the model per request.
        * If :http:method:`post` is in this list, the API will allow posting a
          new instance of the model per request.

        The default set of methods provides a read-only interface (that is,
        only :http:method:`get` requests are allowed).

        `collection_name` is the name of the collection specified by the given
        model class to be used in the URL for the ReSTful API created. If this
        is not specified, the lowercase name of the model will be used.

        `url_prefix` the URL prefix at which this API will be accessible.

        If `allow_patch_many` is ``True``, then requests to
        :http:patch:`/api/<collection_name>?q=<searchjson>` will attempt to
        patch the attributes on each of the instances of the model which match
        the specified search query. This is ``False`` by default. For
        information on the search query parameter ``q``, see
        :ref:`searchformat`.

        `validation_exceptions` is the tuple of possible exceptions raised by
        validation of your database models. If this is specified, validation
        errors will be captured and forwarded to the client in JSON format. For
        more information on how to use validation, see :ref:`validation`.

        If `allow_functions` is ``True``, then requests to
        :http:get:`/api/eval/<collection_name>` will return the result of
        evaluating SQL functions specified in the body of the request. For
        information on the request format, see :ref:`functionevaluation`. This
        if ``False`` by default. Warning: you must not create an API for a
        model whose name is ``'eval'`` if you set this argument to ``True``.

        `authentication_required_for` is a list of HTTP method names (for
        example, ``['POST', 'PATCH']``) for which authentication must be
        required before clients can successfully make requests. If this keyword
        argument is specified, `authentication_function` must also be
        specified. For more information on requiring authentication, see
        :ref:`authentication`.

        `authentication_function` is a function which accepts no arguments and
        returns ``True`` if and only if a client is authorized to make a
        request on an endpoint.

        `include_columns` is a list of strings which name the columns of
        `model` which will be included in the JSON representation of that model
        provided in response to :http:method:`get` requests. Only the named
        columns will be included. If this list includes a string which does not
        name a column in `model`, it will be ignored.

        `patch_columns` is a list of strings which name the columns of
        `model` which will be used for :http:method:`patch`  and
        :http:method:`put` requests. If request includes other columns,
        they will be ignored. If this list includes a string which does not
        name a column in `model`, it will be ignored.

        `results_per_page` is a positive integer which represents the number of
        results which are returned per page. If this is anything except a
        positive integer, pagination will be disabled (warning: this may result
        in large responses). For more information, see :ref:`pagination`.

        `post_form_preprocessor` is a callback function which takes
        POST input parameters loaded from JSON and enhances them with other
        key/value pairs. The example use of this is when your ``model``
        requires to store user identity and for security reasons the identity
        is not read from the post parameters (where malicious user can tamper
        with them) but from the session.

        `post_form_postprocessor` is a callback function which takes
        POST method result on input and further works on it. The example use
        of this function is when you need to generate new CSRF token once
        the call was successfully completed.

        `patch_form_preprocessor` is a callback function which takes
        PUT or PATCH 2 input parameters - instance ID and data loaded from JSON
        and enhances them with other key/value pairs. The example use of this
        is when your ``model`` requires to store user identity and for security
        reasons the identity is not read from the post parameters (where
        malicious user can tamper with them) but from the session.

        `patch_form_postprocessor` is a callback function which takes
        PUT or PATCH method result on input and further works on it. The example use
        of this function is when you need to generate new CSRF token once
        the call was successfully completed. Is used only in case when single
        instance is being updated.

        `delete_form_preprocessor` is a callback function which takes
        SQLAlchemy model instance as input parameter (if found) and performs an
        action on it. The example use of this is when you need to check access
        rights for the DELETE action. The function is executed only if instance
        to be deleted exists in the system.

        `delete_form_postprocessor` is a callback function which instance ID
        as an input parameter and further works on it. The example use
        of this function is when you need to generate new CSRF token once
        the call was successfully completed.

        `get_result_postprocessor` is a callback function which takes
        GET output and enhances it with other key/value pairs.

        `get_request_preprocessor` is a callback function which takes
        GET input and enhances it as required.

        .. versionadded:: 0.6
           This functionality was formerly in :meth:`create_api`, but the
           blueprint creation and registration have now been separated.

        .. versionadded:: 0.6
           Added the `results_per_page` keyword argument.

        .. versionadded:: 0.5
           Added the `include_columns` and `validation_exceptions` keyword
           argument.

        .. versionadded:: 0.4
           Added the `allow_functions`, `allow_patch_many`,
           `authentication_required_for`, `authentication_function`, and
           `collection_name` keyword arguments.

        .. versionadded:: 0.4
           Force the model name in the URL to lowercase.

        """
        if authentication_required_for and not authentication_function:
            msg = ('If authentication_required is specified, so must'
                   ' authentication_function.')
            raise IllegalArgumentError(msg)
        if collection_name is None:
            collection_name = model.__tablename__
        # convert all method names to upper case
        methods = frozenset((m.upper() for m in methods))
        # sets of methods used for different types of endpoints
        no_instance_methods = methods & frozenset(('POST', ))
        if allow_patch_many:
            possibly_empty_instance_methods = \
                methods & frozenset(('GET', 'PATCH', 'PUT'))
        else:
            possibly_empty_instance_methods = methods & frozenset(('GET', ))
        instance_methods = \
            methods & frozenset(('GET', 'PATCH', 'DELETE', 'PUT'))
        # the base URL of the endpoints on which requests will be made
        collection_endpoint = '/%s' % collection_name
        # the name of the API, for use in creating the view and the blueprint
        apiname = APIManager.APINAME_FORMAT % collection_name
        # the view function for the API for this model
        api_view = API.as_view(apiname, self.session, model,
                               authentication_required_for,
                               authentication_function, include_columns,
                               patch_columns,
                               validation_exceptions, results_per_page,
                               post_form_preprocessor,
                               post_form_postprocessor,
                               patch_form_preprocessor,
                               patch_form_postprocessor,
                               delete_form_preprocessor,
                               delete_form_postprocessor,
                               get_result_postprocessor,
                               get_request_preprocessor)
        # suffix an integer to apiname according to already existing blueprints
        blueprintname = self._next_blueprint_name(apiname)
        # add the URL rules to the blueprint: the first is for methods on the
        # collection only, the second is for methods which may or may not
        # specify an instance, the third is for methods which must specify an
        # instance
        # TODO what should the second argument here be?
        # TODO should the url_prefix be specified here or in register_blueprint
        blueprint = Blueprint(blueprintname, __name__, url_prefix=url_prefix)
        blueprint.add_url_rule(collection_endpoint,
                               methods=no_instance_methods, view_func=api_view)
        blueprint.add_url_rule(collection_endpoint, defaults={'instid': None},
                               methods=possibly_empty_instance_methods,
                               view_func=api_view)
        # the per-instance endpoints will allow both integer and string primary
        # key accesses
        for converter in ('int', 'string'):
            instance_endpoint = '%s/<%s:instid>' % (collection_endpoint,
                                                    converter)
            blueprint.add_url_rule(instance_endpoint, methods=instance_methods,
                                   view_func=api_view)
        # endpoints for instance related collections - one-to-many relation only
        for relname in _get_onetomany_relations(model):
            view = _related_collection(api_view, relname)
            for converter in ('int', 'string'):
                instance_endpoint = '%s/<%s:instid>/%s/' % (collection_endpoint,
                                                            converter, relname)
                blueprint.add_url_rule(instance_endpoint, methods=['GET'],
                                       view_func=view)
        # if function evaluation is allowed, add an endpoint at /api/eval/...
        # which responds only to GET requests and responds with the result of
        # evaluating functions on all instances of the specified model
        if allow_functions:
            eval_api_name = apiname + 'eval'
            eval_api_view = FunctionAPI.as_view(eval_api_name, self.session,
                                                model)
            eval_endpoint = '/eval' + collection_endpoint
            blueprint.add_url_rule(eval_endpoint, methods=['GET'],
                                   view_func=eval_api_view)
        return blueprint

    def create_api(self, *args, **kw):
        """Creates and registers a ReSTful API blueprint on the
        :class:`flask.Flask` application specified in the constructor of this
        class.

        The positional and keyword arguments are passed directly to the
        :meth:`create_api_blueprint` method, so see the documentation there.

        This is a convenience method for the following code::

            blueprint = apimanager.create_api_blueprint(*args, **kw)
            app.register_blueprint(blueprint)

        .. versionchanged:: 0.6
           The blueprint creation has been moved to
           :meth:`create_api_blueprint`; the registration remains here.

        """
        blueprint = self.create_api_blueprint(*args, **kw)
        self.app.register_blueprint(blueprint)
