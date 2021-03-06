from distutils.command.build_ext import build_ext
from distutils.errors import CCompilerError
from distutils.errors import DistutilsExecError
from distutils.errors import DistutilsPlatformError
import os
import platform
import re
import sys

from setuptools import Distribution as _Distribution
from setuptools import Extension
from setuptools import find_packages
from setuptools import setup
from setuptools.command.test import test as TestCommand


cmdclass = {}
if sys.version_info < (2, 7):
    raise Exception("SQLAlchemy requires Python 2.7 or higher.")

cpython = platform.python_implementation() == "CPython"

ext_errors = (CCompilerError, DistutilsExecError, DistutilsPlatformError)
if sys.platform == "win32":
    # Work around issue https://github.com/pypa/setuptools/issues/1902
    ext_errors += (IOError, TypeError)
    extra_compile_args = []
elif sys.platform == "linux":
    # warn for undefined symbols in .c files
    extra_compile_args = ["-Wundef"]
else:
    extra_compile_args = []

ext_modules = [
    Extension(
        "sqlalchemy.cprocessors",
        sources=["lib/sqlalchemy/cextension/processors.c"],
        extra_compile_args=extra_compile_args,
    ),
    Extension(
        "sqlalchemy.cresultproxy",
        sources=["lib/sqlalchemy/cextension/resultproxy.c"],
        extra_compile_args=extra_compile_args,
    ),
    Extension(
        "sqlalchemy.cutils",
        sources=["lib/sqlalchemy/cextension/utils.c"],
        extra_compile_args=extra_compile_args,
    ),
]


class BuildFailed(Exception):
    def __init__(self):
        self.cause = sys.exc_info()[1]  # work around py 2/3 different syntax


class ve_build_ext(build_ext):
    # This class allows C extension building to fail.

    def run(self):
        try:
            build_ext.run(self)
        except DistutilsPlatformError:
            raise BuildFailed()

    def build_extension(self, ext):
        try:
            build_ext.build_extension(self, ext)
        except ext_errors:
            raise BuildFailed()
        except ValueError:
            # this can happen on Windows 64 bit, see Python issue 7511
            if "'path'" in str(sys.exc_info()[1]):  # works with both py 2/3
                raise BuildFailed()
            raise


cmdclass["build_ext"] = ve_build_ext


class Distribution(_Distribution):
    def has_ext_modules(self):
        # We want to always claim that we have ext_modules. This will be fine
        # if we don't actually have them (such as on PyPy) because nothing
        # will get built, however we don't want to provide an overally broad
        # Wheel package when building a wheel without C support. This will
        # ensure that Wheel knows to treat us as if the build output is
        # platform specific.
        return True


class UseTox(TestCommand):
    RED = 31
    RESET_SEQ = "\033[0m"
    BOLD_SEQ = "\033[1m"
    COLOR_SEQ = "\033[1;%dm"

    def run_tests(self):
        sys.stderr.write(
            "%s%spython setup.py test is deprecated by pypa.  Please invoke "
            "'tox' with no arguments for a basic test run.\n%s"
            % (self.COLOR_SEQ % self.RED, self.BOLD_SEQ, self.RESET_SEQ)
        )
        sys.exit(1)


cmdclass["test"] = UseTox


def status_msgs(*msgs):
    print("*" * 75)
    for msg in msgs:
        print(msg)
    print("*" * 75)


with open(
    os.path.join(os.path.dirname(__file__), "lib", "sqlalchemy", "__init__.py")
) as v_file:
    VERSION = (
        re.compile(r""".*__version__ = ["'](.*?)['"]""", re.S)
        .match(v_file.read())
        .group(1)
    )

with open(os.path.join(os.path.dirname(__file__), "README.rst")) as r_file:
    readme = r_file.read()


def run_setup(with_cext):
    kwargs = {}
    if with_cext:
        kwargs["ext_modules"] = ext_modules
    else:
        if os.environ.get("REQUIRE_SQLALCHEMY_CEXT"):
            raise AssertionError(
                "Can't build on this platform with "
                "REQUIRE_SQLALCHEMY_CEXT set."
            )

        kwargs["ext_modules"] = []

    setup(
        name="SQLAlchemy",
        version=VERSION,
        description="Database Abstraction Library",
        author="Mike Bayer",
        author_email="mike_mp@zzzcomputing.com",
        url="http://www.sqlalchemy.org",
        project_urls={
            "Documentation": "https://docs.sqlalchemy.org",
            "Issue Tracker": "https://github.com/sqlalchemy/sqlalchemy/",
        },
        packages=find_packages("lib"),
        package_dir={"": "lib"},
        license="MIT",
        cmdclass=cmdclass,
        long_description=readme,
        python_requires=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*",
        classifiers=[
            "Development Status :: 5 - Production/Stable",
            "Intended Audience :: Developers",
            "License :: OSI Approved :: MIT License",
            "Programming Language :: Python",
            "Programming Language :: Python :: 2",
            "Programming Language :: Python :: 2.7",
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.5",
            "Programming Language :: Python :: 3.6",
            "Programming Language :: Python :: 3.7",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: Implementation :: CPython",
            "Programming Language :: Python :: Implementation :: PyPy",
            "Topic :: Database :: Front-Ends",
            "Operating System :: OS Independent",
        ],
        distclass=Distribution,
        extras_require={
            "mysql": ["mysqlclient"],
            "pymysql": ["pymysql"],
            "postgresql": ["psycopg2"],
            "postgresql_psycopg2binary": ["psycopg2-binary"],
            "postgresql_pg8000": ["pg8000"],
            "postgresql_psycopg2cffi": ["psycopg2cffi"],
            "oracle": ["cx_oracle"],
            "mssql_pyodbc": ["pyodbc"],
            "mssql_pymssql": ["pymssql"],
            "mssql": ["pyodbc"],
        },
        **kwargs
    )


if not cpython:
    run_setup(False)
    status_msgs(
        "WARNING: C extensions are not supported on "
        + "this Python platform, speedups are not enabled.",
        "Plain-Python build succeeded.",
    )
elif os.environ.get("DISABLE_SQLALCHEMY_CEXT"):
    run_setup(False)
    status_msgs(
        "DISABLE_SQLALCHEMY_CEXT is set; "
        + "not attempting to build C extensions.",
        "Plain-Python build succeeded.",
    )

else:
    try:
        run_setup(True)
    except BuildFailed as exc:

        if os.environ.get("REQUIRE_SQLALCHEMY_CEXT"):
            status_msgs(
                "NOTE: C extension build is required because "
                "REQUIRE_SQLALCHEMY_CEXT is set, and the build has failed; "
                "will not degrade to non-C extensions"
            )
            raise

        status_msgs(
            exc.cause,
            "WARNING: The C extension could not be compiled, "
            + "speedups are not enabled.",
            "Failure information, if any, is above.",
            "Retrying the build without the C extension now.",
        )

        run_setup(False)

        status_msgs(
            "WARNING: The C extension could not be compiled, "
            + "speedups are not enabled.",
            "Plain-Python build succeeded.",
        )
