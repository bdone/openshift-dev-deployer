# import requests
import pystache
import os
import subprocess
from getpass import getpass
import json
import sys
import base64


def get_rh_id(default):
    rh_id = input('RH subscription-manager ID [' +
                  default + ']:')
    rh_id = rh_id or default
    return rh_id


def get_reg_pool(default):
    reg_pool = input('RH subscription pool id (RHEL) [' +
                     default + ']:')
    reg_pool = reg_pool or default
    return reg_pool


def get_ec2_key(default):
    ec2_key = input('ec2 key name [' +
                    default + ']:')
    ec2_key = ec2_key or default
    return ec2_key


def get_git_ssh_file(default):
    git_ssh_file = input('ssh key for source repo  [' +
                         default + ']:')
    git_ssh_file = git_ssh_file or default
    return git_ssh_file


def get_user_script_file(default):
    user_script_file = input('Optional script to run inside openshift container.' +
                             '\nUse this to configure apps, policies, etc. [' +
                             default + ']:')
    user_script_file = user_script_file or default
    return user_script_file


def get_rh_password(default):
    rh_password = getpass('Subscription Manager password ' +
                          '[cached password]:')
    rh_password = rh_password or default
    return rh_password


def get_ose_admin_password(default):
    ose_admin_password = getpass('Openshift admin password ' +
                                 '[cached password]:')
    ose_admin_password = ose_admin_password or default
    return ose_admin_password


def main():
    # deploys all in one OSE on ec2
    # you can see what was passed as user-data to an ec2 instance by doing
    # curl -s http://169.254.169.254/latest/user-data
    # on the instance.

    # first check for ec2 credentials
    f = open(os.environ['HOME'] + '/.aws/credentials', 'r')
    f.read()
    f.close()

    f = open(os.environ['HOME'] + "/.aws/config", 'r')
    f.read()
    f.close()

    try:
        f = open(os.environ['HOME'] + '/.deploy-ose.json', 'r')
        cached_deploy_json = f.read()
        f.close
        cached_deploy_dict = json.loads(cached_deploy_json)

    except:
        cached_deploy_dict = {'rh_id': '',
                              'rh_password': '',
                              'reg_pool': '',
                              'ec2_key': '',
                              'git_ssh_file': '',
                              'ose_admin_password': '',
                              'user_script_file': ""}

    rh_id = ''
    while not rh_id:
        rh_id = get_rh_id(cached_deploy_dict['rh_id'])

    rh_password = ''
    while not rh_password:
        rh_password = \
          get_rh_password(cached_deploy_dict['rh_password'])

    reg_pool = ''
    while not reg_pool:
        reg_pool = \
          get_reg_pool(cached_deploy_dict['reg_pool'])

    ec2_key = ''
    while not ec2_key:
        ec2_key = get_ec2_key(cached_deploy_dict['ec2_key'])

    ose_admin_password = ''
    while not ose_admin_password:
        ose_admin_password = \
          get_ose_admin_password(cached_deploy_dict['ose_admin_password'])

    git_ssh_file = ''
    while not git_ssh_file:
        git_ssh_file = get_git_ssh_file(cached_deploy_dict['git_ssh_file'])

    # check to make sure the git ssh key exists and we can access it
    try:
        f = open(git_ssh_file, 'r')
        git_ssh_key = f.read()
        f.close()
    except:
        print("Could not read ssh key.")
        exit

    # No while because this parameter is optional.
    user_script_file = ''
    user_script_file = get_user_script_file(cached_deploy_dict['user_script_file'])

    # read import-is.sh

    f = open('resources/import-is.sh', 'r')
    import_is = f.read()
    import_is_b64 = base64.b64encode(import_is.encode('utf-8'))
    f.close

    # read optional openshift-config script if it was provided
    if user_script_file != "":
        try:
            f = open(user_script_file, 'r')
            user_script = f.read()
            user_script_b64 = base64.b64encode(user_script.encode('utf-8'))
            f.close
        except e:
            # print("Error opening user script file")
            sys.exit(2)

    if user_script_b64 == "":
        user_script_exec = ""
    else:
        # if there is a user script
        # adds this to the cloud-init script
        user_script_exec = \
            'source /root/deploy-ose/user-script.sh'

    # get the deploy script
    f = open('resources/deploy-ose.stache', 'r')
    script_template = f.read()
    f.close

    # dict of values that are passed to pystache for substitution
    # in deploy-ose.stache
    deploy_dict = {'rh_id': rh_id,
                   'rh_password': rh_password,
                   'reg_pool': reg_pool,
                   'git_ssh_key': git_ssh_key,
                   'ec2_key': ec2_key,
                   'user_script_exec': user_script_exec,
                   'user_script_b64': user_script_b64,
                   'import_is_b64': import_is_b64}

    # create a cache dictionary to write later
    deploy_cache = {'rh_id': rh_id,
                    'reg_pool': reg_pool,
                    'git_ssh_file': git_ssh_file,
                    'ec2_key': ec2_key,
                    'ose_admin_password': ose_admin_password,
                    'rh_password': rh_password,
                    'user_script_file': user_script_file}

    # write the settings to cache file
    f = open(os.environ['HOME'] + '/.deploy-ose.json', 'w')
    f.write(json.dumps(deploy_cache))
    f.close

    # secure the cache file as it contains passwords
    os.chmod(os.environ['HOME'] + '/.deploy-ose.json', 0o600)

    script = pystache.render(script_template, deploy_dict)
    f = open(os.environ['HOME'] + '/cloud-init.sh', 'w')
    f.write(script)
    f.close

    json_result = subprocess.check_output(["aws",
                                           "ec2",
                                           "run-instances",
                                           "--image-id",
                                           "ami-775e4f16",
                                           "--instance-type",
                                           "t2.medium",
                                           "--key-name",
                                           ec2_key,
                                           "--security-groups",
                                           "launch-wizard-1",
                                           "--user-data",
                                           script,
                                           # "file://" + os.environ['HOME'] + '/cloud-init.yaml',
                                           "--block-device-mappings",
                                           '''[{\"DeviceName\":\"/dev/sdb\",\"Ebs\":{\"VolumeSize\":50,\"DeleteOnTermination\":true}},{\"DeviceName\":\"/dev/sdc\",\"Ebs\":{\"VolumeSize\":20,\"DeleteOnTermination\":true}}]'''],
                                          stderr=subprocess.STDOUT)

    print(json_result)  # this was just '0' for success. need stdout.

    # get the id from json_result and tag the instance with the RH username
    # that created it

    print("")
    print("")
    print("")
    print("Settings cached in " + os.environ['HOME'] + '/.deploy-ose.json')
    print("")


if __name__ == "__main__":
    main()
