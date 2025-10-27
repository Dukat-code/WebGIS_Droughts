import argparse
import csv

################################################################
# This script generates an SLD file based on a CSV input file.
# The CSV should have columns: LowerBoundary, UpperBoundary, color
# The generated SLD will contain rules for styling based on these boundaries.
# Usage:
# python generate_sld.py --name style_name --csv input.csv [--title "Style Title"] [--abstract "Style Abstract"]
################################################################
def generate_sld(style_name, csv_file, title="Colors", abstract="Colors depending on value"):
    rules = []
    with open(csv_file, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            lower = row.get('LowerBoundary', '').strip()
            upper = row.get('UpperBoundary', '').strip()
            color = row['color']
            # Generate rule based on boundaries
            if lower and upper:
                # Both boundaries exist: between
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
            elif lower and not upper:
                # Only lower exists: greater than or equal
                rule = f"""
        <Rule>
          <Title>&ge; {lower}</Title>
          <ogc:Filter>
            <ogc:PropertyIsGreaterThanOrEqualTo>
              <ogc:PropertyName>value</ogc:PropertyName>
              <ogc:Literal>{lower}</ogc:Literal>
            </ogc:PropertyIsGreaterThanOrEqualTo>
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
            elif upper and not lower:
                # Only upper exists: less than or equal
                rule = f"""
        <Rule>
          <Title>&le; {upper}</Title>
          <ogc:Filter>
            <ogc:PropertyIsLessThanOrEqualTo>
              <ogc:PropertyName>value</ogc:PropertyName>
              <ogc:Literal>{upper}</ogc:Literal>
            </ogc:PropertyIsLessThanOrEqualTo>
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
            else:
                continue  # skip rows with neither boundary
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