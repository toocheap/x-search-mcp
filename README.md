## **Overview**

Recorded Future Collective Insights is a type of analytics that provides clients a complete view of what threats matters to their organization. Collective Insights aggregates detections across client integrations confirming indicators related to malicious behavior or high-risk activity. This helps TI and SecOps users better prevent and protect client networks by prioritizing actions based on which detections and TTPs are most common across their networks. This article will walk through how to setup Collective Insights for CrowdStrike using the [Recorded Future Collective Insights API](https://support.recordedfuture.com/hc/en-us/articles/15847735339923-Collective-Insights-API).

The following script will ingest detections from CrowdStrike Falcon with behaviors from the previous 24 hours. This timeframe can be adjusted to backfill any additional collective insights. The behaviors from these detections are then filtered by a user set severity and confidence score to determine what is sent off to Recorded Future’s Collective Insights API.

Fields collected from each detection by Recorded Future:

- `id` - The ID of a detection
- `name` - The description of a behavior
- `timestamp` - The timestamp of a behavior associated with a detection
- `type` - The behavior IOC type
- `value` - The behavior IOC value

## **Prerequisites**

The following items be installed/gathered before the setup of the integration script

1. Python v3.8 or greater must be installed
2. Client must have CrowdStrike Falcon
3. Client must be able to host the script in an environment with internet access and file write access.
   1. Server/Workstation for script to run on schedule
   2. Internet Access to Recorded Future API & CrowdStrike Falcon API
   3. Whitelisted [api.recordedfuture.com](http://api.recordedfuture.com/)
   4. Ability to write log files to the script directory
4. Client must have Recorded Future API Token with access to Collective Insights API
   1. This can be provided by your consultant or account team
5. Client must have the following from CrowdStrike in order for the script to retrieve your CrowdStrike Access Token:

   1. CrowdStrike Client ID
   2. CrowdStrike Client Secret

      1. [CrowdStrike Falcon API](https://www.crowdstrike.com/blog/tech-center/get-access-falcon-apis/)

# **Installation**

The CrowdStrike Collective Insights Python script can be found on the Recorded Future support pages or by speaking to your account team.

Once package has been provided and downloaded to the machine where installation will be ran the following steps can be taken to configure and run the script for the first time.

You may opt to store client credentials/secrets as environment variables instead of passing them as parameters to the script. If you choose to do so, you will need to set the following environment variables:

- `RF_API_KEY`: Recorded Future API Key
- `CS_CLIENT_ID`: CrowdStrike Client ID
- `CS_CLIENT_SECRET`: CrowdStrike Client Secret

Set-up Instructions

1. Setup a new virtual environment to install dependencies and run the script from:`virtualenv venv --python=python3.8`
2. Activate new virtual environment:`. venv/bin/activate`
3. Install dependencies from requirements.txt: `pip3 install -r requirements.txt`
4. Run python script manually to confirm deployment is successful: `python CS-Collective_Insights.py -k RF_API_KEY -ccid CROWDSTRIKE_CLIENT_ID -ccs CROWDSTRIKE_CLIENT_SECRET`
5. Setup script to run on schedule daily to ingest events and send to collective insights:
   1. Example cron schedule to run at 00:15: `15 0 * * * <FILE_DIR>/venv/bin/python3 <FILE_DIR>/CS-Collective_Insights.py -k RF_API_KEY -ccid CROWDSTRIKE_CLIENT_ID -ccs CROWDSTRIKE_CLIENT_SECRET`

# **Troubleshooting**

The below section is for providing assistance with troubleshooting when having issues running the script.

- Script is failing due to modules not installed.
  - Try confirming either the requirements.txt was installed properly with pip3 and by running `pip freeze` to confirm the modules are installed.
  - Confirm that the virtual environment where the python packages were installed is activated
- Not authorized to submit to Recorded Future Collective Insights API
  - Confirm that the Recorded Future API token has the correct Collective Insights API permissions activated
- Not authorized to collect events from CrowdStrike Falcon
  - Confirm that the correct Access Levels & Permissions are enabled for the client ID & client secret
    - [CrowdStrike Falcon API](https://www.crowdstrike.com/blog/tech-center/get-access-falcon-apis/)
  - Confirm that the RF API Key, CS Client ID, & CS Client Secret are in the correct parameter locations in the script
- Why am I ingesting 800 events from CrowdStrike but the log says I’ve only submitted 200 indicators?
  - Collective Insights has filtering for unique indicators when submitting via the API.
