from conans import ConanFile, tools
from conans.errors import ConanInvalidConfiguration, ConanException
import os
import shutil
import subprocess


class MSYS2Conan(ConanFile):
    name = "msys2"
    description = "MSYS2 is a software distro and building platform for Windows"
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "http://www.msys2.org"
    license = "MSYS license"
    topics = ("conan", "msys", "unix", "subsystem")
    short_paths = True
    # "exclude_files" "packages" "additional_packages" values are a comma separated list
    options = {
        "exclude_files": "ANY",
        "packages": "ANY",
        "additional_packages": "ANY"
    }
    default_options = {
        "exclude_files": "*/link.exe",
        "packages": "base-devel,binutils,gcc",
        "additional_packages": None
    }
    settings = "os", "arch"

    def validate(self):
        if self.settings.os != "Windows":
            raise ConanInvalidConfiguration("Only Windows supported")
        if tools.Version(self.version) >= "20210105" and self.settings.arch != "x86_64":
            raise ConanInvalidConfiguration("Only Windows x64 supported")
        if tools.Version(self.version) <= "20161025":
            raise ConanInvalidConfiguration("msys2 v.20161025 is no longer supported")    

    def _download(self, url, sha256):
        from six.moves.urllib.parse import urlparse
        filename = os.path.basename(urlparse(url[0]).path)
        tools.download(url=url, filename=filename, sha256=sha256)
        return filename

    @property
    def _keyring_subfolder(self):
        return os.path.join(self.source_folder, "keyring")

    @property
    def _keyring_file(self):
        return os.path.join(self._keyring_subfolder, "msys2-keyring-r21.b39fb11-1-any.pkg.tar.xz")
    
    @property
    def _keyring_sig(self):
        return os.path.join(self._keyring_subfolder, "msys2-keyring-r21.b39fb11-1-any.pkg.tar.xz.sig")    

    # download the new keyring
    # https://www.msys2.org/news/#2020-06-29-new-packagers
    def _download_keyring(self):
        tools.download( "http://repo.msys2.org/msys/x86_64/msys2-keyring-r21.b39fb11-1-any.pkg.tar.xz",
                        self._keyring_file,
                        sha256="f1cc152902fd6018868b64d015cab9bf547ff9789d8bd7c0d798fb2b22367b2b" )
        tools.download( "http://repo.msys2.org/msys/x86_64/msys2-keyring-r21.b39fb11-1-any.pkg.tar.xz.sig",
                        self._keyring_sig,
                        sha256="bbd22e88f33c81c40b145c34d8027d60f714d4fd1d0dccd456895f398cc56297" )

    def _install_pacman_keyring(self):
        with tools.chdir(os.path.join(self._msys_dir, "usr", "bin")):
            self.run('bash -l -c  "pacman-key --init;pacman-key --populate"')
            verify_command = 'bash -l -c "pacman-key --verify %s"' % self._keyring_sig.replace("\\", "/")
            self.run(verify_command)

            install_command = 'bash -l -c "pacman -U %s --noconfirm"' % self._keyring_file.replace("\\", "/")
            self.run(install_command)
            self._kill_pacman()

    def _update_very_old_pacman(self):
        if (tools.Version(self.version) < "20200517"):
            # Fix (https://github.com/msys2/MSYS2-packages/issues/1967)
            # install zstd and pacman manually
            pacman_packages_x64=["http://repo.msys2.org/msys/x86_64/libzstd-1.4.4-2-x86_64.pkg.tar.xz",
                                 "http://repo.msys2.org/msys/x86_64/zstd-1.4.4-2-x86_64.pkg.tar.xz",
                                 "http://repo.msys2.org/msys/x86_64/pacman-5.2.1-6-x86_64.pkg.tar.xz"]
            
            if (self.settings.arch == "x86_64"):
                for i in pacman_packages_x64:
                    self.run('bash -l -c "pacman --noconfirm -U %s"' % i)

            pacman_packages_x32=["http://repo.msys2.org/msys/i686/libzstd-1.4.4-2-i686.pkg.tar.xz",
                                 "http://repo.msys2.org/msys/i686/zstd-1.4.4-2-i686.pkg.tar.xz",
                                 "http://repo.msys2.org/msys/i686/pacman-5.2.1-6-i686.pkg.tar.xz"]

            if (self.settings.arch == "x86"):                     
                for i in pacman_packages_x32:
                    self.run('bash -l -c "pacman --noconfirm -U %s"' % i)

            self._kill_pacman()


    def _update_pacman(self):
        with tools.chdir(os.path.join(self._msys_dir, "usr", "bin")):
            self._update_very_old_pacman()

            # https://www.msys2.org/news/   see  2020-05-31 - Update may fail with "could not open file"
            # update pacman separately first
            self.run('bash -l -c "pacman --noconfirm -Sydd pacman"')

            # https://www.msys2.org/docs/ci/
            self.run('bash -l -c "pacman --noconfirm -Syuu"')  # Core update (in case any core packages are outdated)
            self._kill_pacman()
            self.run('bash -l -c "pacman --noconfirm -Syuu"')  # Normal update
            self._kill_pacman()
            self.run('bash -l -c "pacman -Rc dash --noconfirm"')

    # https://github.com/msys2/MSYS2-packages/issues/1966
    def _kill_pacman(self):
        if (self.settings.os == "Windows"):
            taskkill_exe = os.path.join(os.environ.get('SystemRoot'), 'system32', 'taskkill.exe')

            log_out = True
            if log_out:
                out = subprocess.PIPE
                err = subprocess.STDOUT
            else:
                out = file(os.devnull, 'w')
                err = subprocess.PIPE

            if os.path.exists(taskkill_exe):
                taskkill_cmd1 = taskkill_exe + " /f /t /im pacman.exe"
                taskkill_cmd2 = taskkill_exe + " /f /im gpg-agent.exe"
                taskkill_cmd3 = taskkill_exe + " /f /im dirmngr.exe"

                taskkill_cmd4 = taskkill_exe + ' /fi "MODULES eq msys-2.0.dll"'

                try:
                    proc = subprocess.Popen(taskkill_cmd1, stdout=out, stderr=err, bufsize=1)
                    proc = subprocess.Popen(taskkill_cmd2, stdout=out, stderr=err, bufsize=1)
                    proc = subprocess.Popen(taskkill_cmd3, stdout=out, stderr=err, bufsize=1)

                    proc = subprocess.Popen(taskkill_cmd4, stdout=out, stderr=err, bufsize=1)
                except OSError as e:
                    if e.errno == errno.ENOENT:
                        raise ConanException("Cannot kill pacman")

    @property
    def _msys_dir(self):
        return "msys64" if (tools.Version(self.version) >= "20210105" or self.settings.arch == "x86_64") else "msys32"

    def source(self):
        arch = 1 if self.settings.arch == "x86" else 0  # index in the sources list
        filename = self._download(**self.conan_data["sources"][self.version][arch])
        tools.unzip(filename)
        self._download_keyring()

    def build(self):
        packages = []
        if self.options.packages:
            packages.extend(str(self.options.packages).split(","))
        if self.options.additional_packages:
            packages.extend(str(self.options.additional_packages).split(","))

        if (tools.Version(self.version) < "20210105"):
            self._install_pacman_keyring()
            self._update_pacman()

        with tools.chdir(os.path.join(self._msys_dir, "usr", "bin")):
            for package in packages:
                self.run('bash -l -c "pacman -S %s --noconfirm"' % package)

        # create /tmp dir in order to avoid
        # bash.exe: warning: could not find /tmp, please create!
        tmp_dir = os.path.join(self._msys_dir, 'tmp')
        if not os.path.isdir(tmp_dir):
            os.makedirs(tmp_dir)
        tmp_name = os.path.join(tmp_dir, 'dummy')
        with open(tmp_name, 'a'):
            os.utime(tmp_name, None)

        # Prepend the PKG_CONFIG_PATH environment variable with an eventual PKG_CONFIG_PATH environment variable
        tools.replace_in_file(os.path.join(self._msys_dir, "etc", "profile"),
                              'PKG_CONFIG_PATH="', 'PKG_CONFIG_PATH="$PKG_CONFIG_PATH:')

    def package(self):
        excludes = None
        if self.options.exclude_files:
            excludes = tuple(str(self.options.exclude_files).split(","))
        self.copy("*", dst="bin", src=self._msys_dir, excludes=excludes)
        shutil.copytree(os.path.join(self.package_folder, "bin", "usr", "share", "licenses"),
                        os.path.join(self.package_folder, "licenses"))

    def package_info(self):
        msys_root = os.path.join(self.package_folder, "bin")
        msys_bin = os.path.join(msys_root, "usr", "bin")

        self.output.info("Creating MSYS_ROOT env var : %s" % msys_root)
        self.env_info.MSYS_ROOT = msys_root

        self.output.info("Creating MSYS_BIN env var : %s" % msys_bin)
        self.env_info.MSYS_BIN = msys_bin

        self.output.info("Appending PATH env var with : " + msys_bin)
        self.env_info.path.append(msys_bin)
