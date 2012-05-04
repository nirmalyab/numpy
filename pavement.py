"""
This paver file is intented to help with the release process as much as
possible. It relies on virtualenv to generate 'bootstrap' environments as
independent from the user system as possible (e.g. to make sure the sphinx doc
is built against the built numpy, not an installed one).

Building a fancy dmg from scratch
=================================

Clone the numpy-macosx-installer git repo from on github into the source tree
(numpy-macosx-installer should be in the same directory as setup.py). Then, do
as follows::

    git clone git://github.com/cournape/macosx-numpy-installer
    # remove build dir, and everything generated by previous paver calls
    # (included generated installers). Use with care !
    paver nuke
    paver bootstrap && source bootstrap/bin/activate
    # Installing numpy is necessary to build the correct documentation (because
    # of autodoc)
    python setupegg.py install
    paver dmg

Building a simple (no-superpack) windows installer from wine
============================================================

It assumes that blas/lapack are in c:\local\lib inside drive_c. Build python
2.5 and python 2.6 installers.

    paver bdist_wininst_simple

You will have to configure your wine python locations (WINE_PYS).

The superpack requires all the atlas libraries for every arch to be installed
(see SITECFG), and can then be built as follows::

    paver bdist_superpack

Building changelog + notes
==========================

Assumes you have git and the binaries/tarballs in installers/::

    paver write_release
    paver write_note

This automatically put the checksum into NOTES.txt, and write the Changelog
which can be uploaded to sourceforge.

TODO
====
    - the script is messy, lots of global variables
    - make it more easily customizable (through command line args)
    - missing targets: install & test, sdist test, debian packaging
    - fix bdist_mpkg: we build the same source twice -> how to make sure we use
      the same underlying python for egg install in venv and for bdist_mpkg
"""

# What need to be installed to build everything on mac os x:
#   - wine: python 2.6 and 2.5 + makensis + cpuid plugin + mingw, all in the PATH
#   - paver + virtualenv
#   - full texlive
import os
import sys
import shutil
import subprocess
import re
try:
    from hashlib import md5
except ImportError:
    from md5 import md5

import paver
from paver.easy import \
    options, Bunch, task, call_task, sh, needs, cmdopts, dry

sys.path.insert(0, os.path.dirname(__file__))
try:
    setup_py = __import__("setup")
    FULLVERSION = setup_py.VERSION
    # This is duplicated from setup.py
    if os.path.exists('.git'):
        GIT_REVISION = setup_py.git_version()
    elif os.path.exists('numpy/version.py'):
        # must be a source distribution, use existing version file
        from numpy.version import git_revision as GIT_REVISION
    else:
        GIT_REVISION = "Unknown"

    if not setup_py.ISRELEASED:
        FULLVERSION += '.dev-' + GIT_REVISION[:7]
finally:
    sys.path.pop(0)


#-----------------------------------
# Things to be changed for a release
#-----------------------------------

# Source of the release notes
RELEASE_NOTES = 'doc/release/1.6.2-notes.rst'

# Start/end of the log (from git)
LOG_START = 'v1.5.0'
LOG_END = 'v1.6.1'


#-------------------------------------------------------
# Hardcoded build/install dirs, virtualenv options, etc.
#-------------------------------------------------------
DEFAULT_PYTHON = "2.6"

# Where to put the final installers, as put on sourceforge
SUPERPACK_BUILD = 'build-superpack'
SUPERPACK_BINDIR = os.path.join(SUPERPACK_BUILD, 'binaries')

options(bootstrap=Bunch(bootstrap_dir="bootstrap"),
        virtualenv=Bunch(packages_to_install=["sphinx==1.1.3", "numpydoc"],
                         no_site_packages=False),
        sphinx=Bunch(builddir="build", sourcedir="source", docroot='doc'),
        superpack=Bunch(builddir="build-superpack"),
        installers=Bunch(releasedir="release",
                         installersdir=os.path.join("release", "installers")),
        doc=Bunch(doc_root="doc",
            sdir=os.path.join("doc", "source"),
            bdir=os.path.join("doc", "build"),
            bdir_latex=os.path.join("doc", "build", "latex"),
            destdir_pdf=os.path.join("build_doc", "pdf")
        ),
        html=Bunch(builddir=os.path.join("build", "html")),
        dmg=Bunch(python_version=DEFAULT_PYTHON),
        bdist_wininst_simple=Bunch(python_version=DEFAULT_PYTHON),
)

MPKG_PYTHON = {
        "2.5": ["/Library/Frameworks/Python.framework/Versions/2.5/bin/python"],
        "2.6": ["/Library/Frameworks/Python.framework/Versions/2.6/bin/python"],
        "2.7": ["/Library/Frameworks/Python.framework/Versions/2.7/bin/python"],
        "3.1": ["/Library/Frameworks/Python.framework/Versions/3.1/bin/python3"],
        "3.2": ["/Library/Frameworks/Python.framework/Versions/3.2/bin/python3"],
}

SSE3_CFG = {'ATLAS': r'C:\local\lib\yop\sse3'}
SSE2_CFG = {'ATLAS': r'C:\local\lib\yop\sse2'}
NOSSE_CFG = {'BLAS': r'C:\local\lib\yop\nosse', 'LAPACK': r'C:\local\lib\yop\nosse'}

SITECFG = {"sse2" : SSE2_CFG, "sse3" : SSE3_CFG, "nosse" : NOSSE_CFG}

if sys.platform =="darwin":
    WINDOWS_PYTHON = {
        "3.2": ["wine", os.environ['HOME'] + "/.wine/drive_c/Python32/python.exe"],
        "3.1": ["wine", os.environ['HOME'] + "/.wine/drive_c/Python31/python.exe"],
        "2.7": ["wine", os.environ['HOME'] + "/.wine/drive_c/Python27/python.exe"],
        "2.6": ["wine", os.environ['HOME'] + "/.wine/drive_c/Python26/python.exe"],
        "2.5": ["wine", os.environ['HOME'] + "/.wine/drive_c/Python25/python.exe"]
    }
    WINDOWS_ENV = os.environ
    WINDOWS_ENV["DYLD_FALLBACK_LIBRARY_PATH"] = "/usr/X11/lib:/usr/lib"
    MAKENSIS = ["wine", "makensis"]
elif sys.platform == "win32":
    WINDOWS_PYTHON = {
        "3.2": ["C:\Python32\python.exe"],
        "3.1": ["C:\Python31\python.exe"],
        "2.7": ["C:\Python27\python.exe"],
        "2.6": ["C:\Python26\python.exe"],
        "2.5": ["C:\Python25\python.exe"],
    }
    # XXX: find out which env variable is necessary to avoid the pb with python
    # 2.6 and random module when importing tempfile
    WINDOWS_ENV = os.environ
    MAKENSIS = ["makensis"]
else:
    WINDOWS_PYTHON = {
        "3.2": ["wine", os.environ['HOME'] + "/.wine/drive_c/Python32/python.exe"],
        "3.1": ["wine", os.environ['HOME'] + "/.wine/drive_c/Python31/python.exe"],
        "2.7": ["wine", os.environ['HOME'] + "/.wine/drive_c/Python27/python.exe"],
        "2.6": ["wine", os.environ['HOME'] + "/.wine/drive_c/Python26/python.exe"],
        "2.5": ["wine", os.environ['HOME'] + "/.wine/drive_c/Python25/python.exe"]
    }
    WINDOWS_ENV = os.environ
    MAKENSIS = ["wine", "makensis"]


#-------------------
# Windows installers
#-------------------
def superpack_name(pyver, numver):
    """Return the filename of the superpack installer."""
    return 'numpy-%s-win32-superpack-python%s.exe' % (numver, pyver)

def internal_wininst_name(arch):
    """Return the name of the wininst as it will be inside the superpack (i.e.
    with the arch encoded."""
    ext = '.exe'
    return "numpy-%s-%s%s" % (FULLVERSION, arch, ext)

def wininst_name(pyver):
    """Return the name of the installer built by wininst command."""
    ext = '.exe'
    return "numpy-%s.win32-py%s%s" % (FULLVERSION, pyver, ext)

def prepare_nsis_script(pyver, numver):
    if not os.path.exists(SUPERPACK_BUILD):
        os.makedirs(SUPERPACK_BUILD)

    tpl = os.path.join('tools/win32build/nsis_scripts', 'numpy-superinstaller.nsi.in')
    source = open(tpl, 'r')
    target = open(os.path.join(SUPERPACK_BUILD, 'numpy-superinstaller.nsi'), 'w')

    installer_name = superpack_name(pyver, numver)
    cnt = "".join(source.readlines())
    cnt = cnt.replace('@NUMPY_INSTALLER_NAME@', installer_name)
    for arch in ['nosse', 'sse2', 'sse3']:
        cnt = cnt.replace('@%s_BINARY@' % arch.upper(),
                          internal_wininst_name(arch))

    target.write(cnt)

def bdist_wininst_arch(pyver, arch):
    """Arch specific wininst build."""
    if os.path.exists("build"):
        shutil.rmtree("build")

    _bdist_wininst(pyver, SITECFG[arch])

@task
@cmdopts([("python-version=", "p", "python version")])
def bdist_superpack(options):
    """Build all arch specific wininst installers."""
    pyver = options.python_version
    def copy_bdist(arch):
        # Copy the wininst in dist into the release directory
        if int(pyver[0]) >= 3:
            source = os.path.join('build', 'py3k', 'dist', wininst_name(pyver))
        else:
            source = os.path.join('dist', wininst_name(pyver))
        target = os.path.join(SUPERPACK_BINDIR, internal_wininst_name(arch))
        if os.path.exists(target):
            os.remove(target)
        if not os.path.exists(os.path.dirname(target)):
            os.makedirs(os.path.dirname(target))
        try:
            os.rename(source, target)
        except OSError:
            # When git is installed on OS X but not under Wine, the name of the
            # .exe has "-Unknown" in it instead of the correct git revision.
            # Try to fix this here:
            revidx = source.index(".dev-") + 5
            gitrev = source[revidx:revidx+7]
            os.rename(source.replace(gitrev, "Unknown"), target)

    bdist_wininst_arch(pyver, 'nosse')
    copy_bdist("nosse")
    bdist_wininst_arch(pyver, 'sse2')
    copy_bdist("sse2")
    bdist_wininst_arch(pyver, 'sse3')
    copy_bdist("sse3")

    idirs = options.installers.installersdir
    pyver = options.python_version
    prepare_nsis_script(pyver, FULLVERSION)
    subprocess.check_call(MAKENSIS + ['numpy-superinstaller.nsi'],
                          cwd=SUPERPACK_BUILD)

    # Copy the superpack into installers dir
    if not os.path.exists(idirs):
        os.makedirs(idirs)

    source = os.path.join(SUPERPACK_BUILD, superpack_name(pyver, FULLVERSION))
    target = os.path.join(idirs, superpack_name(pyver, FULLVERSION))
    shutil.copy(source, target)

@task
@cmdopts([("python-version=", "p", "python version")])
def bdist_wininst_nosse(options):
    """Build the nosse wininst installer."""
    bdist_wininst_arch(options.python_version, 'nosse')

@task
@cmdopts([("python-version=", "p", "python version")])
def bdist_wininst_sse2(options):
    """Build the sse2 wininst installer."""
    bdist_wininst_arch(options.python_version, 'sse2')

@task
@cmdopts([("python-version=", "p", "python version")])
def bdist_wininst_sse3(options):
    """Build the sse3 wininst installer."""
    bdist_wininst_arch(options.python_version, 'sse3')

@task
@cmdopts([("python-version=", "p", "python version")])
def bdist_wininst_simple():
    """Simple wininst-based installer."""
    pyver = options.bdist_wininst_simple.python_version
    _bdist_wininst(pyver)

def _bdist_wininst(pyver, cfg_env=None):
    cmd = WINDOWS_PYTHON[pyver] + ['setup.py', 'build', '-c', 'mingw32', 'bdist_wininst']
    if cfg_env:
        for k, v in WINDOWS_ENV.items():
            cfg_env[k] = v
    else:
        cfg_env = WINDOWS_ENV
    subprocess.check_call(cmd, env=cfg_env)

#----------------
# Bootstrap stuff
#----------------
@task
def bootstrap(options):
    """create virtualenv in ./bootstrap"""
    try:
        import virtualenv
    except ImportError, e:
        raise RuntimeError("virtualenv is needed for bootstrap")

    bdir = options.bootstrap_dir
    if not os.path.exists(bdir):
        os.makedirs(bdir)
    bscript = "boostrap.py"

    options.virtualenv.script_name = os.path.join(options.bootstrap_dir,
                                                  bscript)
    options.virtualenv.no_site_packages = False
    options.bootstrap.no_site_packages = False
    call_task('paver.virtual.bootstrap')
    sh('cd %s; %s %s' % (bdir, sys.executable, bscript))

@task
def clean():
    """Remove build, dist, egg-info garbage."""
    d = ['build', 'dist', 'numpy.egg-info']
    for i in d:
        if os.path.exists(i):
            shutil.rmtree(i)

    bdir = os.path.join('doc', options.sphinx.builddir)
    if os.path.exists(bdir):
        shutil.rmtree(bdir)

@task
def clean_bootstrap():
    bdir = os.path.join(options.bootstrap.bootstrap_dir)
    if os.path.exists(bdir):
        shutil.rmtree(bdir)

@task
@needs('clean', 'clean_bootstrap')
def nuke(options):
    """Remove everything: build dir, installers, bootstrap dirs, etc..."""
    for d in [options.superpack.builddir, options.installers.releasedir]:
        if os.path.exists(d):
            shutil.rmtree(d)

#---------------------
# Documentation tasks
#---------------------
@task
def html(options):
    """Build numpy documentation and put it into build/docs"""
    # Don't use paver html target because of numpy bootstrapping problems
    bdir = os.path.join("doc", options.sphinx.builddir, "html")
    if os.path.exists(bdir):
        shutil.rmtree(bdir)
    subprocess.check_call(["make", "html"], cwd="doc")
    html_destdir = options.html.builddir
    if os.path.exists(html_destdir):
        shutil.rmtree(html_destdir)
    shutil.copytree(bdir, html_destdir)

@task
def latex():
    """Build numpy documentation in latex format."""
    subprocess.check_call(["make", "latex"], cwd="doc")

@task
@needs('latex')
def pdf():
    sdir = options.doc.sdir
    bdir = options.doc.bdir
    bdir_latex = options.doc.bdir_latex
    destdir_pdf = options.doc.destdir_pdf

    def build_pdf():
        subprocess.check_call(["make", "all-pdf"], cwd=str(bdir_latex))
    dry("Build pdf doc", build_pdf)

    if os.path.exists(destdir_pdf):
        shutil.rmtree(destdir_pdf)
    os.makedirs(destdir_pdf)

    user = os.path.join(bdir_latex, "numpy-user.pdf")
    shutil.copy(user, os.path.join(destdir_pdf, "userguide.pdf"))
    ref = os.path.join(bdir_latex, "numpy-ref.pdf")
    shutil.copy(ref, os.path.join(destdir_pdf, "reference.pdf"))

#------------------
# Mac OS X targets
#------------------
def dmg_name(fullversion, pyver, osxver=None):
    """Return name for dmg installer.

    Notes
    -----
    Python 2.7 has two binaries, one for 10.3 (ppc, i386) and one for 10.6
    (i386, x86_64). All other Python versions at python.org at the moment
    have binaries for 10.3 only. The "macosx%s" part of the dmg name should
    correspond to the python.org naming scheme.
    """
    # assume that for the py2.7/osx10.6 build the deployment target is set
    # (should be done in the release script).
    if not osxver:
        osxver = os.environ.get('MACOSX_DEPLOYMENT_TARGET', '10.3')
    return "numpy-%s-py%s-python.org-macosx%s.dmg" % (fullversion, pyver,
                                                      osxver)

def macosx_version():
    if not sys.platform == 'darwin':
        raise ValueError("Not darwin ??")
    st = subprocess.Popen(["sw_vers"], stdout=subprocess.PIPE)
    out = st.stdout.readlines()
    ver = re.compile("ProductVersion:\s+([0-9]+)\.([0-9]+)\.([0-9]+)")
    for i in out:
        m = ver.match(i)
        if m:
            return m.groups()

def mpkg_name(pyver):
    maj, min = macosx_version()[:2]
    # Note that bdist_mpkg breaks this if building a dev version with a git
    # commit string attached. make_fullplatcomponents() in
    # bdist_mpkg/cmd_bdist_mpkg.py replaces '-' with '_', comment this out if
    # needed.
    return "numpy-%s-py%s-macosx%s.%s.mpkg" % (FULLVERSION, pyver, maj, min)

def _build_mpkg(pyver):
    # account for differences between Python 2.7.1 versions from python.org
    if os.environ.get('MACOSX_DEPLOYMENT_TARGET', None) == "10.6":
        ldflags = "-undefined dynamic_lookup -bundle -arch i386 -arch x86_64 -Wl,-search_paths_first"
    else:
        ldflags = "-undefined dynamic_lookup -bundle -arch i386 -arch ppc -Wl,-search_paths_first"
    ldflags += " -L%s" % os.path.join(os.path.dirname(__file__), "build")

    if pyver == "2.5":
        sh("CC=gcc-4.0 LDFLAGS='%s' %s setupegg.py bdist_mpkg" % (ldflags, " ".join(MPKG_PYTHON[pyver])))
    else:
        sh("LDFLAGS='%s' %s setupegg.py bdist_mpkg" % (ldflags, " ".join(MPKG_PYTHON[pyver])))

@task
def simple_dmg():
    pyver = "2.6"
    src_dir = "dmg-source"

    # Clean the source dir
    if os.path.exists(src_dir):
        shutil.rmtree(src_dir)
    os.makedirs(src_dir)

    # Build the mpkg
    clean()
    _build_mpkg(pyver)

    # Build the dmg
    shutil.copytree(os.path.join("dist", mpkg_name(pyver)),
                    os.path.join(src_dir, mpkg_name(pyver)))
    _create_dmg(pyver, src_dir, "NumPy Universal %s" % FULLVERSION)

@task
def bdist_mpkg(options):
    call_task("clean")
    try:
        pyver = options.bdist_mpkg.python_version
    except AttributeError:
        pyver = options.python_version

    _build_mpkg(pyver)

def _create_dmg(pyver, src_dir, volname=None):
    # Build the dmg
    image_name = dmg_name(FULLVERSION, pyver)
    if os.path.exists(image_name):
        os.remove(image_name)
    cmd = ["hdiutil", "create", image_name, "-srcdir", src_dir]
    if volname:
        cmd.extend(["-volname", "'%s'" % volname])
    sh(" ".join(cmd))

@task
@cmdopts([("python-version=", "p", "python version")])
def dmg(options):
    try:
        pyver = options.dmg.python_version
    except:
        pyver = DEFAULT_PYTHON
    idirs = options.installers.installersdir

    # Check if docs exist. If not, say so and quit.
    ref = os.path.join(options.doc.destdir_pdf, "reference.pdf")
    user = os.path.join(options.doc.destdir_pdf, "userguide.pdf")
    if (not os.path.exists(ref)) or (not os.path.exists(user)):
        import warnings
        warnings.warn("Docs need to be built first! Can't find them.")

    # Build the mpkg package
    call_task("clean")
    _build_mpkg(pyver)

    macosx_installer_dir = "tools/numpy-macosx-installer"
    dmg = os.path.join(macosx_installer_dir, dmg_name(FULLVERSION, pyver))
    if os.path.exists(dmg):
        os.remove(dmg)

    # Clean the image source
    content = os.path.join(macosx_installer_dir, 'content')
    if os.path.exists(content):
        shutil.rmtree(content)
    os.makedirs(content)

    # Copy mpkg into image source
    mpkg_source = os.path.join("dist", mpkg_name(pyver))
    mpkg_target = os.path.join(content, "numpy-%s-py%s.mpkg" % (FULLVERSION, pyver))
    shutil.copytree(mpkg_source, mpkg_target)

    # Copy docs into image source
    pdf_docs = os.path.join(content, "Documentation")
    if os.path.exists(pdf_docs):
        shutil.rmtree(pdf_docs)
    os.makedirs(pdf_docs)
    shutil.copy(user, os.path.join(pdf_docs, "userguide.pdf"))
    shutil.copy(ref, os.path.join(pdf_docs, "reference.pdf"))

    # Build the dmg
    cmd = ["./new-create-dmg", "--pkgname", os.path.basename(mpkg_target),
        "--volname", "numpy", os.path.basename(dmg), "./content"]
    st = subprocess.check_call(cmd, cwd=macosx_installer_dir)

    source = dmg
    target = os.path.join(idirs, os.path.basename(dmg))
    if not os.path.exists(os.path.dirname(target)):
        os.makedirs(os.path.dirname(target))
    shutil.copy(source, target)

#--------------------------
# Source distribution stuff
#--------------------------
def tarball_name(type='gztar'):
    root = 'numpy-%s' % FULLVERSION
    if type == 'gztar':
        return root + '.tar.gz'
    elif type == 'zip':
        return root + '.zip'
    raise ValueError("Unknown type %s" % type)

@task
def sdist(options):
    # To be sure to bypass paver when building sdist... paver + numpy.distutils
    # do not play well together.
    sh('python setup.py sdist --formats=gztar,zip')

    # Copy the superpack into installers dir
    idirs = options.installers.installersdir
    if not os.path.exists(idirs):
        os.makedirs(idirs)

    for t in ['gztar', 'zip']:
        source = os.path.join('dist', tarball_name(t))
        target = os.path.join(idirs, tarball_name(t))
        shutil.copy(source, target)

def compute_md5(idirs):
    released = paver.path.path(idirs).listdir()
    checksums = []
    for f in released:
        m = md5(open(f, 'r').read())
        checksums.append('%s  %s' % (m.hexdigest(), f))

    return checksums

def write_release_task(options, filename='NOTES.txt'):
    idirs = options.installers.installersdir
    source = paver.path.path(RELEASE_NOTES)
    target = paver.path.path(filename)
    if target.exists():
        target.remove()
    source.copy(target)
    ftarget = open(str(target), 'a')
    ftarget.writelines("""
Checksums
=========

""")
    ftarget.writelines(['%s\n' % c for c in compute_md5(idirs)])

def write_log_task(options, filename='Changelog'):
    st = subprocess.Popen(
            ['git', 'log',  '%s..%s' % (LOG_START, LOG_END)],
            stdout=subprocess.PIPE)

    out = st.communicate()[0]
    a = open(filename, 'w')
    a.writelines(out)
    a.close()

@task
def write_release(options):
    write_release_task(options)

@task
def write_log(options):
    write_log_task(options)

@task
def write_release_and_log(options):
    rdir = options.installers.releasedir
    write_release_task(options, os.path.join(rdir, 'NOTES.txt'))
    write_log_task(options, os.path.join(rdir, 'Changelog'))
