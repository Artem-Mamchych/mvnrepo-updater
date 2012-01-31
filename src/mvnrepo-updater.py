description='mvnrepo-updater.py used for batch updating/redeploying maven artifacts on remote server or local machine'
version = 0.6
usage = 'Usage: mvnrepo-updater.py [-u|-U|-d] project_name_1 project_name_2#branch project_name_N'
latest_version_url = "https://raw.github.com/Artem-Mamchych/mvnrepo-updater/master/src/mvnrepo-updater.py"

#Created on Dec 01, 2011
#Author: Artem Mamchych
import sys
import subprocess
import os.path

version_string = "%s version: %s  Latest version available at:\n %s" % (sys.argv[0], str(version), latest_version_url)
home_dir = os.getcwd()
log_file = None
echoMode = False
resetGitRepos = False
action = None
debug_mode = False
rebase_mode = False
skipTests = False
github_username = None
warnings = list()
executed_commands = list()
artifacts_file = 'artifacts.txt'

def initArtifacts():
    applicationStabilityTest()
    Repository.loadFromFile(os.path.join(os.path.dirname(sys.argv[0]), artifacts_file))

#Ckecks in runtime stability of most critical parts of this script
def applicationStabilityTest():
    ro = Artifact('git://github.com/Artem-Mamchych/python-utils.git')
    assert ro.baseUrl == 'github.com' and ro.organisation == 'Artem-Mamchych' and ro.name == 'python-utils', 'Artifact.parseScmUrl(git:url) is broken!'
    ssh = Artifact('git@github.com:Artem-Mamchych/python-utils.git')
    assert ssh.baseUrl == 'github.com' and ssh.organisation == 'Artem-Mamchych' and ssh.name == 'python-utils', 'Artifact.parseScmUrl(ssh_url) is broken!'
    http = Artifact('https://github.com/SpringSource/spring-roo.git')
    assert http.baseUrl == 'github.com' and http.organisation == 'SpringSource' and http.name == 'spring-roo', 'Artifact.parseScmUrl(https_url) is broken!'
    assert http.getGitHubUrl() == "http://github.com/SpringSource/spring-roo"
    assert http.getScmUrl() == "git://github.com/SpringSource/spring-roo.git"

def isGitRepo(dir):
    if isinstance(dir, Artifact):
        dir = dir.getAbsoluteLocationDir()
    if not isinstance(dir, str):
        raise Exception('Error isGitRepo(dir); dir not a string!')
    return os.path.exists(os.path.join(home_dir, dir, '.git'))

def isUncommittedChangesExists():
    return call('git diff --exit-code --quiet', log=False)

def getBranchName():
    current_branch = callAndGetOutput('git symbolic-ref -q HEAD', log=False)
#    if not current_branch.startswith("refs/heads/"):
#        fatal('Failed to get current branch name in dir ' + os.getcwd())
#        sys.exit(1)
    current_branch = current_branch.replace("refs/heads/","")
    current_branch = current_branch.rstrip()
    return current_branch

def isLocalBranchExists(branchName):
    return not call('git show-ref --verify --quiet refs/heads/"%s"' % branchName, log=False)

def switchBranch(artifact, branch):
    if not artifact.branch:
        return True
    if getBranchName() == branch: #Already on branch
        return True
    if isUncommittedChangesExists():
        fatal(artifact.name + ' contains uncommitted changes. Failed to change branch')
        return False
    if branch:
        if isLocalBranchExists(branch):
            call('git checkout "%s"' % branch)
        else:
            call('git checkout --track -b %s remotes/upstream/%s' % (branch,branch))
        if not getBranchName() == branch:
            fatal('Failed to change branch to: ' + branch + ' in ' + artifact.name)
            return False
    return True

def changeDir(artifact_home):
    if isinstance(artifact_home, Artifact):
        artifact_home = artifact_home.getAbsoluteLocationDir()

    if not os.path.exists(artifact_home):
        log("Creating dir: " + artifact_home)
        os.makedirs(artifact_home)
    os.chdir(artifact_home)
    log("We are in " + os.path.realpath('.'))

def gitCloneOrUpdate(repo):
    if not isGitRepo(repo):
        log("Cloning repo: " + repo.getScmUrl() + ' into ' + os.getcwd())
        call('git clone --verbose ' + repo.getScmUrl() + ' .')
        call('git remote rename origin upstream')
        if github_username:
            call('git remote add %s %s' % (github_username, repo.getSshForkUrl()) )
    else:
        #gitReset(repo)
        if isUncommittedChangesExists():
            warning(repo.getLocationDir() + " contains uncommitted changes, update skipped!")
        else:
            log("Updating repo: " + repo.getScmUrl())
            current_branch = getBranchName()
            if current_branch == "master":
                call('git pull ' + repo.getScmUrl())
            else:
                call('git checkout master')
                call('git pull ' + repo.getScmUrl())
                call('git checkout ' + current_branch)
                if rebase_mode:
                    call('git rebase master')
                else:
                    warning(repo.getLocationDir() + " is updated. Rebase your branches. (git rebase master)")

def gitUpdateAndRebase(artifact):
    global rebase_mode
    rebase_mode = True
    gitCloneOrUpdate(artifact)

def gitReset(repo):
    if resetGitRepos and isGitRepo(repo):
        if isUncommittedChangesExists():
            call('git diff > reverted_changes.diff')
        call('echo git reset --hard')

def gitInfo(artifact):
    call('git --no-pager log --pretty=format:"%an %ar %B" -n 1')

def listAction(artifact):
    print(artifact.getAbsoluteLocationDir())

def listBranch(artifact):
    print(artifact.getCurrentBranchGitHubUrl())

def listStatus(artifact):
    if isUncommittedChangesExists():
        print(artifact.name)
        print("UNCOMMITTED FILES; Branch: "+ getBranchName())

def doAction(args):
    selection = list()
    for arg in args:
        if '#' in arg:
            (artifactName, branch) = str.split(arg, '#')
            if not branch:
                branch = 'master'
            warning('Using resolveOne() with switch branch mode: %s#%s' % (artifactName, branch))
            target = Repository.resolveOne(artifactName)
            target.branch = branch
            selection.append(target)
        else:
            Repository.resolve(arg, selection)
    if not selection:
        warning("0 artifacts selected")
        return
    print("doAction() will be executed on the following artifacts:")
    for arg in selection:
        print(arg.name)

    for artifact in selection:
        Repository.applyAction(action, artifact)

#Classes:
#Maven Artifact
class Artifact(object):
    baseUrl = None
    organisation = None
    name = None
    customHomeDir = None
    branch = None

    #url format: 'git://#baseUrl#/#organisation#/#name#.git'
    def __init__(self, scmUrl, path=None):
        (baseUrl, organisation, name) = self.parseScmUrl(scmUrl)
        self.baseUrl = baseUrl
        self.organisation = organisation
        self.name = name
        self.setAbsoluteLocationDir(path)

    def __str__(self):
        return 'Artifact: ' + self.getScmUrl()

    def getLocationDir(self):
        if self.customHomeDir:
            return self.customHomeDir
        return os.path.join(self.organisation, self.name)

    def setAbsoluteLocationDir(self, dir):
        if dir:
            if not os.path.exists(dir):
                os.makedirs(dir)
            self.customHomeDir = dir

    def getAbsoluteLocationDir(self):
        path = os.path.join(home_dir, self.organisation, self.name)
        if self.customHomeDir:
            if os.path.exists(self.customHomeDir):
                return self.customHomeDir
            else:
                fatal("Failed to get %s artifact home dir, using default: %s" % (self.name, path))
        if path:
            return path

    def getOrganisationDir(self):
        return self.organisation

    def getGitHubUrl(self):
        return "http://" + self.baseUrl + '/' + self.organisation + '/' + self.name

    def getScmUrl(self):
        return "git://" + self.baseUrl + '/' + self.organisation + '/' + self.name + ".git"

    def getGitHubForkUrl(self):
        if github_username:
            return "http://" + self.baseUrl + '/' + github_username + '/' + self.name

    def getSshForkUrl(self):
        if github_username:
            return "git@" + self.baseUrl + ':' + github_username + '/' + self.name + ".git"

    def getCurrentBranchGitHubUrl(self):
        fork = self.organisation
        if github_username:
            fork = github_username
        return "http://" + self.baseUrl + '/' + fork + '/' + self.name + '/commits/' + getBranchName()

    @staticmethod
    def parseScmUrl(url):
        url = url.replace('https://', '')
        url = url.replace('http://', '')
        url = url.replace('.git', '')
        url = url.replace('git://', '')
        url = url.replace('git@', '')
        url = url.replace(':', '/')

        out = url.split("/")
        if isinstance(out, list) and len(out) == 3:
            return out
        else:
            return [None, None, None]

class Action(object):
    name = None
    callback = None
    changedir = False
    silentMode = False
    printName = False

    def __init__(self, name, callback, silentMode=False, changedir=True, printName=False):
        self.name = name
        self.callback = callback
        self.changedir = changedir
        self.silentMode = silentMode
        self.printName = printName

    def execute(self, artifact):
        if self.callback:
            if self.changedir:
                changeDir(artifact)
            if self.silentMode:
                silentMode()
            if self.printName:
                print(artifact.name)
            if switchBranch(artifact, artifact.branch):
                self.callback(artifact)
            else:
                fatal('Action skipped for ' + artifact.name + ' failed to switch branch!')
        else:
            print('Action callback function is not set')

class MavenGoal(Action):
    maven_command = None
    gitUpdate = None

    def __init__(self, name, command, gitUpdate=False):
        self.name = name
        self.maven_command = command
        self.gitUpdate = gitUpdate

    def execute(self, artifact):
        changeDir(artifact)
        if not isGitRepo(artifact) or self.gitUpdate:
            gitCloneOrUpdate(artifact)
        if switchBranch(artifact, artifact.branch):
            #TODO if self.gitUpdate: run git pull??
            maven(self.maven_command)
        else:
            fatal('Action skipped for ' + artifact.name + ' failed to switch branch!')

def default(name):
    print('DefaultAction empty callback function')

class Repository(object):
    artifacts = list()
    action_map = dict()
    default_action = Action('default', default, silentMode=False, changedir=False)

    @staticmethod
    def put(repo):
        Repository.artifacts.append(repo)

    @staticmethod
    def addAction(action):
        if isinstance(action, Action):
            Repository.action_map[action.name] = action

    @staticmethod
    def applyAction(name, target):
        action = Repository.action_map.get(name, Repository.default_action)
        action.execute(target)

    #artifacts_list will be populated by all artifacts, which contains 'name' in name
    @staticmethod
    def resolve(name, artifacts_list):
        if isinstance(name, list) and len(name) == 1:
            name = name[0]
        if not isinstance(name, str):
            error_mesg = "getArtifactsByName(name= type:%s) not a string!" % str(type(name))
            log(error_mesg)
            raise Exception(error_mesg)

        for repo in Repository.artifacts:
            if name == '*' or (repo.name and name in repo.name):
                artifacts_list.append(repo)

    #Resolve artifact by name
    @staticmethod
    def resolveOne(name):
        artifact = None
        for repo in Repository.artifacts:
            if name == repo.name:
                artifact = repo
        if not artifact:
            print("Failed to resolve artifact, unknown name: " + name)
            sys.exit()
        return artifact

    @staticmethod
    def loadFromFile(filename):
        if not os.path.exists(filename):
            fatal("Failed to load artifact urls from file! File '%s' is not exists" % filename)
            sys.exit(1)
        if not os.path.isfile(filename):
            fatal("Failed to load artifact urls from file! '%s' is not a file" % filename)
            sys.exit(2)
        urls_file = open(filename)
        lines = urls_file.readlines()
        urls_file.close()
        for line in lines:
            line = line.strip()
            if line:
                Repository.put(Artifact(line))

def callAndGetOutput(cmd, log=True):
    if log:
        logExecutedCommand(cmd)
    if echoMode:
        return ""

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (stdoutdata, stderrdata) = process.communicate()
        if stdoutdata:
            log2file("STDOUT: ")
            log2file(stdoutdata)
        if stderrdata:
            logExecutedCommand("!!STDERR: " + str(stderrdata))
        if sys.version_info >= (3, 0):
            return str(stdoutdata, "utf-8") #converts binary string
        else:
            return str(stdoutdata)
    except Exception:
        warning('[Error] executing command: ' + cmd)
        warning(str(sys.exc_info()[1]))

def call(cmd, log=True):
    if log:
        logExecutedCommand(cmd)
    if not echoMode:
        try:
            return subprocess.call(cmd, shell=True)
        except Exception:
            warning('[Error] executing command: ' + cmd)
            warning(str(sys.exc_info()[1]))

def maven(cmd):
    if sys.platform.startswith('win32'):
        cmd = 'mvn.bat ' + cmd
    else:
        cmd = 'mvn ' + cmd
    if skipTests:
        cmd += ' -Dmaven.test.skip=true'
    call(cmd)

def fatal(mesg):
    log2file('!FATAL! ' + mesg)
    print(mesg)

def log(mesg):
    log2file('[DEBUG] ' + mesg)
    if debug_mode:
        print(mesg)

def silentMode():
    global debug_mode
    debug_mode = False

#All warning messages are cached and will be printed only on showWarnings() call
def warning(mesg):
    if mesg:
        log2file('[WARN] ' + mesg)
        warnings.append(mesg)

def showWarnings():
    if warnings:
        print("Warning messages:")
    for text in warnings:
        print(text)

#All commands are cached and will be printed only on showExecutedCommands() call
def logExecutedCommand(cmd):
    log2file('call ' + cmd)
    executed_commands.append(cmd)

def showExecutedCommands():
    if executed_commands:
        print('Commands below was executed in shell:')
    for command in executed_commands:
        print(command)

def log2file(mesg):
    global log_file
    if not log_file:
        log_file = open(os.path.join(home_dir, '.mvnrepo-updater.log'), 'a')
    log_file.write("\n" + str(mesg))

def main():
    from optparse import OptionParser
    parser = OptionParser(usage=usage, description=description, version=version_string)
    parser.add_option("-D", "--Debug", action="store_true", dest="debug", default=False,
        help="Debug mode (Shows debug messages)")
    parser.add_option("-S", "--skip-tests", action="store_true", dest="skipTests", default=False,
        help="Skip tests in all maven goals")
    parser.add_option("-G", "--github-username", dest="github_username",
        help="Sets github username. Used to add git remote with this github username", metavar="GITHUB_USERNAME")
    parser.add_option("-a", "--apps-home", dest="apps_home",
        help="Projects location directory (git clone directory)", metavar="APPS_DIR")
    parser.add_option("-e", action="store_true", dest="echoMode", default=False,
        help="Echo mode. All external commands will not be executed")
    parser.add_option("-R", "--reset", action="store_true", dest="resetGitRepos", default=False,
        help="Reset all uncommitted changes")

    parser.add_option("-u", "--update", action="store_const",
        const="update", dest="action", help="Clone or update artifacts")
    Repository.addAction(Action("update", gitCloneOrUpdate, silentMode=False, changedir=True, printName=False))
    parser.add_option("-U", "--update-rebase", action="store_const",
        const="rebase", dest="action", help="Clone or update artifacts with rebase. UNSAFE if conflict occurs while rebasing multiple projects")
    Repository.addAction(Action("rebase", gitUpdateAndRebase, silentMode=False, changedir=True, printName=False))
    parser.add_option("-l", "--list", action="store_const",
        const="list", dest="action", help="List artifacts location dirs")
    Repository.addAction(Action("list", listAction, silentMode=True, changedir=False, printName=False))
    parser.add_option("-L", "--branch", action="store_const",
        const="branch", dest="action", help="List urls of github branches")
    Repository.addAction(Action("branch", listBranch, silentMode=True, changedir=True, printName=False))
    parser.add_option("-i", "--info", action="store_const",
        const="info", dest="action", help="Show info on last commits in working copy: author, date, message")
    Repository.addAction(Action("info", gitInfo, silentMode=True, changedir=True, printName=True))
    parser.add_option("-s", "--status", action="store_const",
        const="status", dest="action", help="Show all artifacts with uncommitted changes")
    Repository.addAction(Action("status", listStatus, silentMode=True, changedir=True, printName=False))
    parser.add_option("-x", "--resolve", action="store_const",
        const="resolve", dest="action", help="Resolve all maven dependencies")
    Repository.addAction(MavenGoal("resolve", 'dependency:resolve dependency:resolve-plugins'))
    parser.add_option("-d", "--deploy", action="store_const",
        const="deploy", dest="action", help="Deploy artifacts")
    Repository.addAction(MavenGoal("deploy", 'clean deploy', gitUpdate=True))
    parser.add_option("-t", "--test", action="store_const",
        const="test", dest="action", help="Run tests")
    Repository.addAction(MavenGoal("test", '-o clean test'))
    parser.add_option("-c", "--clean", action="store_const",
        const="clean", dest="action", help="Clean")
    Repository.addAction(MavenGoal("clean", '-o clean'))

    (options, args) = parser.parse_args()
    global debug_mode
    debug_mode = options.debug
    global echoMode
    echoMode = options.echoMode
    global resetGitRepos
    resetGitRepos = options.resetGitRepos
    global action
    action = options.action
    global github_username
    github_username = options.github_username
    global skipTests
    skipTests = options.skipTests

    global home_dir
    if options.apps_home:
        if os.path.isdir(options.apps_home) and os.path.exists(options.apps_home):
            home_dir = options.apps_home
            log("Dir apps-home is set to path: " + home_dir)
        else:
            log("Bad apps-home argument - path '%s' is not exists or not a directory!" % options.apps_home)
            resetGitRepos = False
            action = None

    import datetime
    now = datetime.datetime.now()
    log2file('\n\t [%s]' % now.strftime("%Y-%m-%d %H:%M"))

    initArtifacts()
    doAction(args)

    log2file("options: " + str(options))
    log2file("artifacts: " + str(args))

    if debug_mode:
        showExecutedCommands()
    showWarnings()
    log2file('All actions finished successfully')
    log_file.close()
    return 0

if __name__ == "__main__":
    main()
