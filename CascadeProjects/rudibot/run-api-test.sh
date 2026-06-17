#!/bin/bash
cd /Users/rudolfsarkany/CascadeProjects/rudibot
node test-all-apis.js > api-test-results.txt 2>&1
echo "Test completed. Results saved to api-test-results.txt"
