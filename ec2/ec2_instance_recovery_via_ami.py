#!/usr/bin/env python
# *-* coding: utf-8 *-*
'''
 WARNING: THIS SCRIPT IS WRITTEN TO WORK TOGETHER WITH EC2 AMI BACKUP SCRIPT (image_bkup.py).
 		  THUS, THIS SCRIPT MIGHT NOT BEHAVE AS EXPECTED WHILING LAUNCHING INSTANCE USING OTHER IMAGE ID
		  ONLY IMAGE ID CREATED BY EC2 AMI BACKUP SCRIPT (image_bkup.py).

 SCRIPT LOGIC
 ------------
 1. Get the AMI ID from user.
 2. Get instance associated with the AMI ID via Tag (InstanceId).
 3. Create new instance from the given AMI ID.
 	3.1. Instance name should be [INSTANCE_NAME]+1.
 	3.2. All the instance attribute should be identical to failed instance.
 4. Detach the EIP associated with the instance.
 	4.1. Instance must have EIP associated, before detaching.
 5. Detach EIP from the failed instance.
 5. Attach EIP to the new instance.
 	5.1. Create EIP tag with associated EIP to new instance.
 6. [optional] Remove the failed instance.

 PREREQUISITE
 ------------
 1. Install AWS CLI and Configure AWS Access Key, Secret Key and Default Region
 	> pip install awscli
 	> aws configure

 HOW TO USE THIS SCRIPT
 ----------------------
	> Use the command-line '--help' options.

 Tested on: Python v2.7.x
'''


## FOR DEBUGGING PURPOSE
ENABLE_DEBUG=True




## WARNING !! WARNING !! ############
## DO NOT CHANGE THE CODE BELOW !!
## YOUR USERNAME/IP WILL BE LOGGED
#####################################




import subprocess as sp
import json
import sys
import optparse

SUCCESS=True
FAILURE=False

def error(message):
	''' display message as error. '''
	message = str(message)
	for line in message.splitlines():
		print('\033[31merror:\033[00m %s' % line)


def warning(message):
	''' display message as warning. '''
	message = str(message)
	for line in message.splitlines():
		print('warning: %s' % line)


def info(message):
	''' display message as informative. '''
	message = str(message)
	for line in message.splitlines():
		print('info: %s' % line)


def convert_json_to_dict(json_str):
	''' convert json string to dict object. '''
	try:
		_dict = json.loads(json_str)
	except Exception as exc:
		info('inside function: convert_json_to_dict')
		raise exc
	return _dict


def run_cmd(cmd):
	''' invoke external command to perform the action and return stdout data.'''
	stdout=''
	if ENABLE_DEBUG:
		info('running command => {}'.format(cmd))
	try:
		popen = sp.Popen(cmd, shell=True, stdout=sp.PIPE, stderr=sp.PIPE)
		popen.wait()
		rcode = popen.returncode
		if ENABLE_DEBUG:
			info("command exit code: "+str(rcode))
		if rcode != 0:
			warning("command exited abnormally with non-zero exit code: "+str(rcode))
		stdout = popen.stdout.read()
		stderr = popen.stderr.read()
		if len(stderr):
			error("error occured while running: {}".format(cmd))
			error(stderr)
			sys.exit(1)
	except Exception as exc:
		info('inside function: run_cmd')
		raise exc
	return stdout


def parse_opts():
	opt = optparse.OptionParser()
	opt.add_option('', '--image-id', dest='image_id', help='Specify EC2 AMI ID to launch instance.', metavar='AMI_ID')
	(opts, args) = opt.parse_args()
	return (opt, opts)


def filter_image_by_image_id(image_id):
	''' filter image by image id and convert return json data to python dict. '''
	cmd = 'aws ec2 describe-images --owners self --image-ids {}'.format(image_id)
	stdout = run_cmd(cmd) 
	return convert_json_to_dict(stdout)


def filter_instance_by_image_id(image_id):
	''' filter instance by image id and convert return json data to python dict. '''
	cmd = 'aws ec2 describe-'	


def filter_instance_id_by_image_id(image_id):
	''' filter instance id by image id and return instance id (string). '''
	info("retreiving instance id associated with image ({})...".format(image_id))
	images = filter_image_by_image_id(image_id)
	instance_id = ''
	for image in images['Images']:
		for tag in image['Tags']:
			if tag['Key'] == 'InstanceId':
				instance_id = tag['Value']
				break
		if instance_id:
			break
	return instance_id 		


def check_tag_eip_by_instance_id(instance_id):
	'''
		retrieve the EIP associated with given instance in the Tags of the instance.
	'''
	info("checking EIP tag associated with instance ({})...".format(instance_id))
	eip = str()
	cmd = 'aws ec2 describe-tags --filters "Name=key,Values=EIP,Name=resource-id,Values={}"'.format(instance_id)
	stdout = run_cmd(cmd)
	tags = convert_json_to_dict(stdout)
	for tag in tags['Tags']:
		if tag['Key'] == 'EIP':
			eip = tag['Value']
			break
	if not eip:
		error("instance ({}) does not have tag EIP attached.".format(instance_id))
		exit(0)
	return eip


def filter_instance_by_instance_id(instance_id):
	cmd = 'aws ec2 describe-instances --instance-ids {INSTANCE_ID}'.format(INSTANCE_ID=instance_id)
	stdout = run_cmd(cmd)
	reservations = convert_json_to_dict(stdout)
	reservation = reservations['Reservations'][0]
	instances = reservation['Instances']
	instance = instances[0]
	return instance


def detach_eip_by_instance_id(eip, instance_id):
	'''
		Detach given EIP from given instance-id.
	'''
	info("detaching EIP '{}' from instance {}...".format(eip, instance_id))
	cmd = 'aws ec2 disassociate-address --public-ip {}'.format(eip)
	stdout = run_cmd(cmd)
	response = convert_json_to_dict(stdout)
	if response["return"] == "true":
		info("successfully detached EIP '{}' from instance {}.".format(eip, instance_id))
		return SUCCESS
	else:
		warning("unable to detach EIP '{}'. Please, troubleshooting manually.".format(eip))
		return FAILURE


def attach_eip_by_instance_id(eip, instance_id):
	'''
		Attach given EIP to instance given its instance-id.
	'''
	info("attaching EIP '{}' to new instance {}...".format(eip, new_instance_id))
	cmd = 'aws ec2 associate-address --instance-id {} --public-ip {}'.format(instance_id, eip)
	stdout = run_cmd(cmd)
	response = convert_json_to_dict(stdout)
	if response["return"] == "true":
		info("successfully attached EIP '{}' to instance {}.".format(eip, instance_id))
	else:
		warning("unable to attach EIP '{}'. Please, troubleshooting manually.".format(eip))
		return FAILURE

	## set EIP tag
	eip_tag = "Key=EIP,Value='{}'".format(eip)
	info('creating tag "{}" for instance ({})...'.format(eip_tag, instance_id))
	cmd = '''aws ec2 create-tags --resources "{}" --tags "{}"'''.format(instance_id, eip_tag)
	# create-tags does not return any data (None)
	run_cmd(cmd)

	return SUCCESS

def replicate_instance_from_image_id(image_id, instance_id=None):
	''' Create new instance given image id with same attribute as given instance_id except instance name which should increment. '''
	
	info("launching new instance from image {} replicating instance {}...".format(image_id, instance_id))
	instance = filter_instance_by_instance_id(instance_id)

	## get instance name or set 'N/A'
	instance_name = str()
	for tag in instance['Tags']:
		if tag['Key'] == 'Name':
			instance_name = tag['Value']
	if not instance_name:
		warning("instance id ({}) does not have 'Name' tag.".format(instance_id))
		instance_name = ''

	## get required values for launching an instances.
	image_id = image_id; key_name = instance['KeyName'];
	security_group = instance['SecurityGroups'][0]['GroupName'];
	instance_type = instance['InstanceType']; kernel_id = instance['KernelId']; 
	## launch instance
	cmd = 'aws ec2 run-instances --image-id {IMAGE_ID} --count 1 --instance-type {INSTANCE_TYPE} --key-name {KEY_NAME} --security-groups {SECURITY_GROUP} --kernel-id {KERNEL_ID}'.format(IMAGE_ID=image_id, INSTANCE_TYPE=instance_type, KEY_NAME=key_name, SECURITY_GROUP=security_group, KERNEL_ID=kernel_id)
	stdout = run_cmd(cmd)

	## get new instance info
	new_reservation = convert_json_to_dict(stdout)
	new_instance = new_reservation['Instances'][0]
	new_instance_name = ''

	# get old instance name and set new instance name
	if instance_name != '':
		instance_name_list = instance_name.rsplit('-')
		instance_counter = int(instance_name_list[-1])
		new_instance_name = '{}-{}'.format('-'.join(instance_name_list[:-1]), str(instance_counter+1).zfill(3))
	else:
		new_instance_name = ''

	new_instance_tag = "Key=Name,Value='{}'".format(new_instance_name)
	new_instance_id = new_instance['InstanceId']
	info('creating tag "{}" for instance ({})...'.format(new_instance_tag, new_instance_id))
	cmd = '''aws ec2 create-tags --resources "{}" --tags "{}"'''.format(new_instance_id, new_instance_tag)
	# create-tags does not return any data (None)
	run_cmd(cmd)

	return new_instance_id

def main():
	(opt, opts) = parse_opts()
	if (opts.image_id == None): opt.print_usage(); exit(1)
	image_id = opts.image_id

	# get associated instance from image using tags
	instance_id = filter_instance_id_by_image_id(image_id)

	# check if instance has EIP tag associated, we need this to associate it to new instance
	eip = check_tag_eip_by_instance_id(instance_id)

	# launch new instance from "image_id" + set unique name
	new_instance_id = replicate_instance_from_image_id(image_id, instance_id)

	# detach eip from old instance
	detach_eip_by_instance_id(eip, instance_id)

	# attach eip to new instance
	attach_eip_by_instance_id(eip, new_instance_id)
	exit(0)

if __name__ == "__main__": main()
