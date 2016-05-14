#!/bin/bash
#
# Writes silo app ids, secrets, and tokens in environment variables to files
# that oauth-dropins reads from the file system. Details in appengine_config.py.

set -e
src=`dirname $0`/../..

