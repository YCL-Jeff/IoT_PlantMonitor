{\rtf1\ansi\ansicpg1252\cocoartf2867
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 #include <Arduino.h>\
#include <DHT.h> // \uc0\u25110 \u20351 \u29992 \u20320 \u23565 \u25033 \u30340 \u24863 \u28204 \u22120 \u24235  (\u22914  AHT10/BME280)\
\
#define DHTPIN 4      // \uc0\u24863 \u28204 \u22120 \u33139 \u20301 \
#define DHTTYPE DHT22 // \uc0\u24863 \u28204 \u22120 \u22411 \u34399 \
\
DHT dht(DHTPIN, DHTTYPE);\
\
void setup() \{\
  Serial.begin(115200);\
  dht.begin();\
\}\
\
void loop() \{\
  // \uc0\u35712 \u21462 \u25976 \u25818 \
  float h = dht.readHumidity();\
  float t = dht.readTemperature();\
\
  // \uc0\u27298 \u26597 \u35712 \u21462 \u26159 \u21542 \u22833 \u25943 \
  if (isnan(h) || isnan(t)) \{\
    // Serial.println("Failed to read from DHT sensor!"); // \uc0\u22833 \u25943 \u26178 \u19981 \u36664 \u20986 \u26684 \u24335 \u37679 \u35492 \u30340 \u23383 \u20018 \
    return;\
  \}\
\
  // \uc0\u36664 \u20986 \u26684 \u24335 : "\u28331 \u24230 ,\u28629 \u24230 " (\u20363 \u22914 : 24.5,60.2)\
  Serial.print(t);\
  Serial.print(",");\
  Serial.println(h);\
\
  delay(1000); // \uc0\u27599 \u31186 \u25505 \u27171 \u19968 \u27425 \u65292 Python \u31471 \u26371 \u33258 \u21205 \u24179 \u28369 \u34389 \u29702 \
\}}