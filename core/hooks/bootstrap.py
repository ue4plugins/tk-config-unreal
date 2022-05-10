# This file is provided by Epic Games, Inc. and is subject to the license
# file included in this repository.

"""
This hook is used override some of the functionality of the :class:`~sgtk.bootstrap.ToolkitManager`.

It will be instantiated only after a configuration has been selected by the :class:`~sgtk.bootstrap.ToolkitManager`.
Therefore, this hook will not be invoked to download a configuration. However, the Toolkit Core,
applications, frameworks and engines can be downloaded through the hook.
"""

import os
import zipfile
import json
import platform
import re

from sgtk import get_hook_baseclass


_SIX_IMPORT_WARNING = (
    "Unable to import six.moves from tk-core, this can happen "
    "if an old version of tk-core < 0.19.1 is used in a site "
    "pipeline configuration. Falling back on using urllib2."
)


class Bootstrap(get_hook_baseclass()):
    """
    Override the bootstrap core hook to cache some bundles ourselves.
    http://developer.shotgunsoftware.com/tk-core/core.html#bootstrap.Bootstrap
    """
    # List of github repos for which we download releases, with a github token to
    # do the download if the repo is private
    _download_release_from_github = [
        ("ue4plugins/tk-framework-unrealqt", ""),
        ("GPLgithub/tk-framework-unrealqt", ""),
    ]

    def can_cache_bundle(self, descriptor):
        """
        Indicates if a bundle can be cached by the :meth:`populate_bundle_cache_entry` method.

        This method is invoked when the bootstrap manager wants to cache a bundle used by a configuration.

        .. note:: This method is not called if the bundle is already cached so it
                  can't be used to update an existing cached bundle.

        :param descriptor: Descriptor of the bundle that needs to be cached.

        :returns: ``True`` if the bundle can be cached with this hook, ``False``
                  if not.
        :rtype: bool
        :raises RuntimeError: If six.moves is not available.
        """
        descd = descriptor.get_dict()
        return bool(self._should_download_release(descd))

    def populate_bundle_cache_entry(self, destination, descriptor, **kwargs):
        """
        Populates an entry from the bundle cache.

        This method will be invoked for every bundle for which :meth:`can_cache_bundle`
        returned ``True``. The hook is responsible for writing the bundle inside
        the destination folder. If an exception is raised by this method, the files
        will be deleted from disk and the bundle cache will be left intact.

        It has to properly copy all the files or the cache for this bundle
        will be left in an inconsistent state.

        :param str destination: Folder where the bundle needs to be written. Note
            that this is not the final destination folder inside the bundle cache.

        :param descriptor: Descriptor of the bundle that needs to be cached.
        """
        # This logic can be removed once we can assume tk-core is > v0.19.1 not
        # just in configs but also in the bundled Shotgun.app.
        try:
            from tank_vendor.six.moves.urllib import request as url2
            from tank_vendor.six.moves.urllib import error as error_url2
        except ImportError as e:
            self.logger.warning(_SIX_IMPORT_WARNING)
            self.logger.debug("%s" % e, exc_info=True)
            # Fallback on using urllib2
            import urllib2 as url2
            import urllib2 as error_url2

        descd = descriptor.get_dict()
        version = descriptor.version
        self.logger.info("Treating %s" % descd)
        specs = self._should_download_release(descd)
        if not specs:
            raise RuntimeError("Don't know how to download %s" % descd)
        name = specs[0]
        token = specs[1]
        try:
            if self.shotgun.config.proxy_handler:
                # Re-use proxy settings from the Shotgun connection
                opener = url2.build_opener(
                    self.parent.shotgun.config.proxy_handler,
                )
                url2.install_opener(opener)

            # Retrieve the release from the tag
            url = "https://api.github.com/repos/%s/releases/tags/%s" % (name, version)
            request = url2.Request(url)
            # Add the authorization token if we have one (private repos)
            if token:
                request.add_header("Authorization", "token %s" % token)
            request.add_header("Accept", "application/vnd.github.v3+json")
            try:
                response = url2.urlopen(request)
            except error_url2.URLError as e:
                if hasattr(e, "code"):
                    if e.code == 404:
                        self.logger.error("Release %s does not exists" % version)
                    elif e.code == 401:
                        self.logger.error("Not authorised to access release %s." % version)
                raise
            response_d = json.loads(response.read())
            # Look up for suitable assets for this platform. Assets names
            # follow this convention:
            #  <version>-py<python version>-<platform>.zip
            # We download and extract all assets for any Python version for
            # the current platform and version. We're assuming that the cached
            # config for a user will never be shared between machines with
            # different os.
            pname = {
                "Darwin": "osx",
                "Linux": "linux",
                "Windows": "win"
            }.get(platform.system())

            if not pname:
                raise ValueError("Unsupported platform %s" % platform.system())

            extracted = []
            for asset in response_d["assets"]:
                name = asset["name"]
                m = re.match(
                    r"%s-py\d.\d-%s.zip" % (version, pname),
                    name
                )
                if m:
                    # Download the asset payload
                    self._download_zip_github_asset(
                        asset,
                        destination,
                        token
                    )
                    extracted.append(asset)

            if not extracted:
                raise RuntimeError(
                    "Couldn't retrieve a suitable asset from %s" % [
                        a["name"] for a in response_d["assets"]
                    ]
                )
            self.logger.info(
                "Extracted files: %s from %s" % (
                    os.listdir(destination),
                    ",".join([a["name"] for a in extracted])
                )
            )
        except Exception as e:
            # Log the exception with the backtrace because TK obfuscates it.
            self.logger.exception(e)
            raise

    def _should_download_release(self, desc):
        """
        Return a repo name and a token if the given descriptor should be downloaded
        from a github release.

        :param str desc: A Toolkit descriptor.
        :returns: A name, token tuple or ``None``.
        """
        if desc["type"] == "github_release":
            # Let's be safe...
            if not desc.get("organization") or not desc.get("repository"):
                return None
            desc_path = "%s/%s" % (desc["organization"], desc["repository"])
            for name, token in self._download_release_from_github:
                if name == desc_path:
                    return name, token
        elif desc.get("path"):
            # Check the path for a git descriptor
            desc_path = desc["path"]
            for name, token in self._download_release_from_github:
                if "git@github.com:%s.git" % name == desc_path:
                    return name, token
        return None

    def _download_zip_github_asset(self, asset, destination, token):
        """
        Download the zipped github asset and extract it into the given destination
        folder.

        Assets can be retrieved with the releases github REST api endpoint.
        https://developer.github.com/v3/repos/releases/#get-a-release-by-tag-name

        :param str asset: A Github asset dictionary.
        :param str destination: Full path to a folder where to extract the downloaded
                            zipped archive. The folder is created if it does not
                            exist.
        :param str token: A Github OAuth or personal token.
        """
        try:
            from tank_vendor.six.moves.urllib import request as url2
        except ImportError as e:
            self.logger.warning(_SIX_IMPORT_WARNING)
            self.logger.debug("%s" % e, exc_info=True)
            # Fallback on using urllib2
            import urllib2 as url2
        # If we have a token use a basic auth handler
        # just a http handler otherwise
        if token:
            passman = url2.HTTPPasswordMgrWithDefaultRealm()
            passman.add_password(
                None,
                asset["url"],
                token,
                token
            )
            auth_handler = url2.HTTPBasicAuthHandler(passman)
        else:
            auth_handler = url2.HTTPHandler()

        if self.shotgun.config.proxy_handler:
            # Re-use proxy settings from the Shotgun connection
            opener = url2.build_opener(
                self.parent.shotgun.config.proxy_handler,
                auth_handler
            )
        else:
            opener = url2.build_opener(auth_handler)

        url2.install_opener(opener)
        request = url2.Request(asset["url"])
        if token:
            # We will be redirected and the Auth shouldn't be in the header
            # for the redirection.
            request.add_unredirected_header("Authorization", "token %s" % token)
        request.add_header("Accept", "application/octet-stream")
        response = url2.urlopen(request)
        if not os.path.exists(destination):
            self.logger.info("Creating %s" % destination)
            os.makedirs(destination)
        tmp_file = os.path.join(destination, asset["name"])
        with open(tmp_file, "wb") as f:
            f.write(response.read())
        with zipfile.ZipFile(tmp_file, "r") as zip_ref:
            zip_ref.extractall(destination)
