#!/bin/bash

java -jar ../lutra.jar --mode expand -I tabottr --library lib --libraryFormat stottr schema/classes.xlsx -o schema/classes.ttl

java -jar ../lutra.jar --mode expand -I tabottr --library lib --libraryFormat stottr schema/classes-ext.xlsx -o schema/classes-ext.ttl

java -jar ../lutra.jar --mode expand -I tabottr --library lib --libraryFormat stottr schema/props.xlsx -o schema/props.ttl