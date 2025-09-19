import requests
from requests.auth import HTTPBasicAuth
import os

# GeoServer connection info
GEOSERVER_URL = "http://localhost:8080/geoserver"
USERNAME = "admin"
PASSWORD = "geoserver"

# Layer info from config
LAYER_NAME = "era5_ecowas_data_view_tst"
WORKSPACE = "droughts"
DATASTORE = "tst"  
STYLE_NAME = "era5_monthly_ecowas"  
DEFAULT_TIME = "1991-01-01"  # Example default time value

# 1. Publish feature type (vector layer)
feature_type_payload = f"""
<featureType>
  <name>{LAYER_NAME}</name>
  <nativeName>{LAYER_NAME}</nativeName>
  <title>{LAYER_NAME}</title>
  <nativeCRS>EPSG:4326</nativeCRS>
  <srs>EPSG:3857</srs>
  <srsHandling>REPROJECT_TO_DECLARED</srsHandling>
  <enabled>true</enabled>
</featureType>
"""

r = requests.post(
    f"{GEOSERVER_URL}/rest/workspaces/{WORKSPACE}/datastores/{DATASTORE}/featuretypes",
    data=feature_type_payload,
    headers={"Content-Type": "text/xml"},
    auth=HTTPBasicAuth(USERNAME, PASSWORD)
)
print("Feature type publish:", r.status_code, r.text)

# 2. Set style
style_payload = f"""
<layer>
  <defaultStyle>
    <name>{STYLE_NAME}</name>
  </defaultStyle>
</layer>
"""

r = requests.put(
    f"{GEOSERVER_URL}/rest/layers/{WORKSPACE}:{LAYER_NAME}",
    data=style_payload,
    headers={"Content-Type": "text/xml"},
    auth=HTTPBasicAuth(USERNAME, PASSWORD)
)
print("Set style:", r.status_code, r.text)

# 3. Enable time dimension
dimension_payload = """
<featureType>
  <metadata>
    <entry key="time">
      <dimensionInfo>
        <enabled>true</enabled>
        <presentation>LIST</presentation>
        <units>ISO8601</units>
        <attribute>date</attribute>
        <defaultValue>{DEFAULT_TIME}</defaultValue>
      </dimensionInfo>
    </entry>
  </metadata>
</featureType>
"""

r = requests.put(
    f"{GEOSERVER_URL}/rest/workspaces/{WORKSPACE}/datastores/{DATASTORE}/featuretypes/{LAYER_NAME}",
    data=dimension_payload,
    headers={"Content-Type": "text/xml"},
    auth=HTTPBasicAuth(USERNAME, PASSWORD)
)
print("Enable time dimension:", r.status_code, r.text)

# 4. Enable tile caching and set gridset (WebMercatorQuad)
gwc_payload = f"""
<layer>
  <name>{WORKSPACE}:{LAYER_NAME}</name>
  <enabled>true</enabled>
  <type>VECTOR</type>
  <defaultStyle>{STYLE_NAME}</defaultStyle>
  <gridSubsets>
    <gridSubset>
      <gridSetName>WebMercatorQuad</gridSetName>
    </gridSubset>
  </gridSubsets>
  <parameterFilters>
    <parameterFilter>
      <key>TIME</key>
      <defaultValue>1991-01-01</defaultValue>
      <regex>.*</regex>
      <type>regex</type>
    </parameterFilter>
  </parameterFilters>
</layer>
"""

r = requests.put(
    f"{GEOSERVER_URL}/gwc/rest/layers/{WORKSPACE}:{LAYER_NAME}.xml",
    data=gwc_payload,
    headers={"Content-Type": "text/xml"},
    auth=HTTPBasicAuth(USERNAME, PASSWORD)
)
print("Enable tile caching:", r.status_code, r.text)