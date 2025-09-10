<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" xmlns:sld="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" version="1.0.0">
  <UserLayer>
    <sld:LayerFeatureConstraints>
      <sld:FeatureTypeConstraint/>
    </sld:LayerFeatureConstraints>
    <sld:UserStyle>
      <sld:Name>spa12_m_gdo_20250101_20250701_m</sld:Name>
      <sld:FeatureTypeStyle>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:Opacity>0.75</sld:Opacity>
            <sld:ChannelSelection>
              <sld:GrayChannel>
                <sld:SourceChannelName>1</sld:SourceChannelName>
              </sld:GrayChannel>
            </sld:ChannelSelection>
            <sld:ColorMap type="intervals">
              <sld:ColorMapEntry color="#ff0000" quantity="-2" label="&lt;= -2.0000"/>
              <sld:ColorMapEntry color="#ffa727" quantity="-1.5" label="-2.0000 - -1.5000"/>
              <sld:ColorMapEntry color="#fffc3b" quantity="-1" label="-1.5000 - -1.0000"/>
              <sld:ColorMapEntry color="#ffffff" quantity="1" label="-1.0000 - 1.0000"/>
              <sld:ColorMapEntry color="#ebcdf7" quantity="1.5" label="1.0000 - 1.5000"/>
              <sld:ColorMapEntry color="#b555c0" quantity="2" label="1.5000 - 2.0000"/>
              <sld:ColorMapEntry color="#7f0b78" quantity="3" label="&gt;= 2.0000"/>
            </sld:ColorMap>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </UserLayer>
</StyledLayerDescriptor>
