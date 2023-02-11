files_rdf:
	java -jar ../lutra.jar --mode expand -I tabottr --library lib --libraryFormat stottr data/xlsx/portal_files.xlsx -o data/portal_files.ttl
  
portals_rdf:
	java -jar ../lutra.jar --mode expand -I tabottr --library lib --libraryFormat stottr data/xlsx/portal_hackies.xlsx -o data/portal_hackies.ttl
	java -jar ../lutra.jar --mode expand -I tabottr --library lib --libraryFormat stottr data/xlsx/portal_studies.xlsx -o data/portal_studies.ttl
	
prov_rdf:
	java -jar ../lutra.jar --mode expand -I tabottr --library lib --libraryFormat stottr data/xlsx/prov.xlsx -o data/prov.ttl

schema_rdf:  
	java -jar ../lutra.jar --mode expand -I tabottr --library lib --libraryFormat stottr schema/classes.xlsx -o schema/classes.ttl
	java -jar ../lutra.jar --mode expand -I tabottr --library lib --libraryFormat stottr schema/classes-ext.xlsx -o schema/classes-ext.ttl
	java -jar ../lutra.jar --mode expand -I tabottr --library lib --libraryFormat stottr schema/props.xlsx -o schema/props.ttl
  
  
