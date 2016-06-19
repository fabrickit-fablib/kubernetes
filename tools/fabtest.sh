#!/bin/bash
#

# exit on error
set -e
flake8 --exclude=test-repo/*

coverage run `which fab` test:l=sample
coverage report
