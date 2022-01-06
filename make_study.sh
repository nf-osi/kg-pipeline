#!/bin/bash

java -jar ../lutra.jar --mode expand -I tabottr --library lib --libraryFormat stottr data/portal_hackies.xlsx -o data/portal_hackies.ttl

java -jar ../lutra.jar --mode expand -I tabottr --library lib --libraryFormat stottr data/portal_studies.xlsx -o data/portal_studies.ttl

