import sys
import os
import logging
import re
from base import scm

class git(scm):
    def switch_revision(self):
        """Switch sources to revision. The git revision may refer to any of the
        following:

        - explicit SHA1: a1b2c3d4....
        - the SHA1 must be reachable from a default clone/fetch (generally, must be
          reachable from some branch or tag on the remote).
        - short branch name: "master", "devel" etc.
        - explicit ref: refs/heads/master, refs/tags/v1.2.3,
          refs/changes/49/11249/1
        """
        if self.revision is None:
            self.revision = 'master'

        found_revision = None
        revs = [x + self.revision for x in ['origin/', '']]
        for rev in revs:
            if self._ref_exists(rev):
                found_revision = True
                if os.getenv('OSC_VERSION'):
                    stash_text = self.helpers.safe_run(['git', 'stash'], cwd=self.clone_dir)[1]
                    text = self.helpers.safe_run(['git', 'reset', '--hard', rev],
                                    cwd=self.clone_dir)[1]
                    if stash_text != "No local changes to save\n":
                        text += self.helpers.safe_run(['git', 'stash', 'pop'],
                                         cwd=self.clone_dir)[1]
                else:
                    text = self.helpers.safe_run(['git', 'reset', '--hard', rev],
                                    cwd=self.clone_dir)[1]
                print text.rstrip()
                break

        if found_revision is None:
            sys.exit('%s: No such revision' % self.revision)

        # only update submodules if they have been enabled
        if os.path.exists(
                os.path.join(self.clone_dir, os.path.join('.git', 'modules'))):
            self.helpers.safe_run(['git', 'submodule', 'update', '--recursive'], cwd=self.clone_dir)

    def fetch_upstream_scm(self):
        """SCM specific version of fetch_uptream for git."""
        if self.args.jailed:
            # FIXME: self.args.cachedir should not be used here
            # gets calculated by get_repocachedir
            lf = open(os.path.join(self.args.cachedir,'.lock'),'w')
            fcntl.lockf(lf,fcntl.LOCK_EX)
            reponame = self.url.split('/')[-1];
            # FIXME: self.args.cachedir should not be used here
            # gets calculated by get_repocachedir
            clone_cache_dir = os.path.join(self.args.cachedir,reponame)
            if not os.path.isfile(os.path.join(clone_cache_dir,'config')):
                # clone if no .git dir exists
                command = ['git', 'clone', '--mirror', self.url, clone_cache_dir]
            else:
                # "git fetch" is a blocking command
                # so no race conditions should occur between multiple service processes
                command = ['git', '-C', clone_cache_dir, 'fetch', '--tags', '--prune']

            self.helpers.safe_run(command, cwd=self.repodir, interactive=sys.stdout.isatty())
            fcntl.lockf(lf,fcntl.LOCK_UN)
            lf.close()

            # We use a temporary shared clone to avoid race conditions
            # between multiple services
            command = ['git','clone',clone_cache_dir,self.url,self.clone_dir]
            use_reference = True
            try:
                if (self.args.package_meta):
                    logging.info("Not using '--reference'")
                    use_reference = False
            except(KeyError):
                pass

            if use_reference:
                command.insert(2,'--reference')
            self.helpers.safe_run(command, cwd=self.repodir, interactive=sys.stdout.isatty())

        else:
            command = ['git', 'clone', self.url, self.clone_dir]

            if not self.is_sslverify_enabled():
                command += ['--config', 'http.sslverify=false']
            self.helpers.safe_run(command, cwd=self.repodir, interactive=sys.stdout.isatty())
            # if the reference does not exist.
            if self.revision and not self._ref_exists(self.revision):
                # fetch reference from url and create locally
                self.helpers.safe_run(['git', 'fetch', self.url, self.revision + ':' + self.revision],
                         cwd=self.clone_dir, interactive=sys.stdout.isatty())

    def fetch_submodules(self):
        """Recursively initialize git submodules."""
        if 'submodules' in self.args.__dict__ and self.args.__dict__['submodules'] == 'enable':
            self.helpers.safe_run(['git', 'submodule', 'update', '--init', '--recursive'],
                     cwd=self.clone_dir)
        elif 'submodules' in self.args.__dict__ and self.args.__dict__['submodules'] == 'master':
            self.helpers.safe_run(['git', 'submodule', 'update', '--init', '--recursive',
                     '--remote'], cwd=self.clone_dir)

    def update_cache(self):
        """Update sources via git."""
        self.helpers.safe_run(['git', 'fetch', '--tags'],
                 cwd=self.clone_dir, interactive=sys.stdout.isatty())
        self.helpers.safe_run(['git', 'fetch'],
                 cwd=self.clone_dir, interactive=sys.stdout.isatty())

    def detect_version(self,args):
        """Automatic detection of version number for checked-out GIT repository."""
        parent_tag      = args['parent_tag']
        versionformat   = args['versionformat']
        if versionformat is None:
            versionformat = '%ct.%h'

        if not parent_tag:
            rc, output = self.helpers.run_cmd(
                            ['git', 'describe', '--tags', '--abbrev=0'],
                            self.clone_dir)
            if rc == 0:
                # strip to remove newlines
                parent_tag = output.strip()
        if re.match('.*@PARENT_TAG@.*', versionformat):
            if parent_tag:
                versionformat = re.sub('@PARENT_TAG@', parent_tag, versionformat)
            else:
                sys.exit("\033[31mNo parent tag present for the checked out "
                         "revision, thus @PARENT_TAG@ cannot be expanded.\033[0m")

        if re.match('.*@TAG_OFFSET@.*', versionformat):
            if parent_tag:
                rc, output = self.helpers.run_cmd(['git', 'rev-list', '--count',
                                      parent_tag + '..HEAD'], self.clone_dir)
                if not rc:
                    tag_offset = output.strip()
                    versionformat = re.sub('@TAG_OFFSET@', tag_offset,
                                           versionformat)
                else:
                    sys.exit("\033[31m@TAG_OFFSET@ can not be expanded: " +
                             output + "\033[0m")
            else:
                sys.exit("\033[31m@TAG_OFFSET@ cannot be expanded, "
                         "as no parent tag was discovered.\033[0m")

        version = self.helpers.safe_run(['git', 'log', '-n1', '--date=short',
                            "--pretty=format:%s" % versionformat], self.clone_dir)[1]
        return self.version_iso_cleanup(version)

    def get_timestamp(self):
        d = {"parent_tag": None, "versionformat": "%ct"}
        timestamp = self.detect_version(d)
        return int(timestamp)

    def get_current_commit(self):
        return  self.helpers.safe_run(['git', 'rev-parse', 'HEAD'], self.clone_dir)[1]

    def _ref_exists(self, rev):
        rc, _ = self.helpers.run_cmd(['git', 'rev-parse', '--verify', '--quiet', rev],
                        cwd=self.clone_dir, interactive=sys.stdout.isatty())
        return (rc == 0)

    def _log_cmd(self, cmd_args, subdir):
        """ Helper function to call 'git log' with args"""
        cmd = ['git', 'log'] + cmd_args
        if subdir:
            cmd += ['--', subdir]
        return self.helpers.safe_run(cmd, cwd=self.clone_dir)[1]


    def detect_changes_scm(self, subdir, changes):
        """Detect changes between GIT revisions."""
        last_rev = changes['revision']

        if last_rev is None:
            last_rev = self._log_cmd(['-n1', '--pretty=format:%H', '--skip=10'],subdir)
        current_rev = self._log_cmd(['-n1', '--pretty=format:%H'],subdir)

        if last_rev == current_rev:
            logging.debug("No new commits, skipping changes file generation")
            return

        dbg_msg = "Generating changes between %s and %s" % (last_rev, current_rev)
        if subdir:
            dbg_msg += " (for subdir: %s)" % (subdir)
        logging.debug(dbg_msg)

        lines = self._log_cmd(['--reverse', '--no-merges', '--pretty=format:%s',
                              "%s..%s" % (last_rev, current_rev)], subdir)

        changes['revision'] = current_rev
        changes['lines'] = lines.split('\n')
        return changes
### END class TarSCM.git
