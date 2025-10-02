import argparse
import csv

def generate_sld(style_name, csv_file, title="Colors", abstract="Colors depending on value"):
    rules = []
    with open(csv_file, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            lower = row['LowerBoundary']
            upper = row['UpperBoundary']
            color = row['color']
            rule = f"""
        <Rule>
          <Title>{lower} - {upper}</Title>
          <ogc:Filter>
            <ogc:PropertyIsBetween>
              <ogc:PropertyName>value</ogc:PropertyName>
              <ogc:LowerBoundary>
                <ogc:Literal>{lower}</ogc:Literal>
              </ogc:LowerBoundary>
              <ogc:UpperBoundary>
                <ogc:Literal>{upper}</ogc:Literal>
              </ogc:UpperBoundary>
            </ogc:PropertyIsBetween>
          </ogc:Filter>
          <PolygonSymbolizer>
            <Fill>
              <CssParameter name="fill">
                <ogc:Literal>{color}</ogc:Literal>
              </CssParameter>
              <CssParameter name="fill-opacity">
                <ogc:Literal>1.0</ogc:Literal>
              </CssParameter>
            </Fill>
          </PolygonSymbolizer>
        </Rule>"""
            rules.append(rule)

    sld_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0" xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc"
  xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd">
  <NamedLayer>
    <Name>{style_name}</Name>
    <UserStyle>
      <Title>{title}</Title>
      <Abstract>{abstract}</Abstract>
      <FeatureTypeStyle>
{''.join(rules)}
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
"""

    with open(f"{style_name}.sld", "w") as out:
        out.write(sld_content)
    print(f"SLD file '{style_name}.sld' generated successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate an SLD file from a CSV.")
    parser.add_argument('--name', required=True, help="Name of the style and output SLD file")
    parser.add_argument('--csv', required=True, help="CSV file with LowerBoundary, UpperBoundary, color columns")
    parser.add_argument('--title', default="Colors", help="Title for the style (default: Colors)")
    parser.add_argument('--abstract', default="Colors depending on value", help="Abstract for the style (default: Colors depending on value)")
    args = parser.parse_args()
    generate_sld(args.name, args.csv, args.title, args.abstract)