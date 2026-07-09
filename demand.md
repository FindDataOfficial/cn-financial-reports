# task1 move the rules to the sqlite, i want to use .env to define the 
databace place, default daas.db





# task2 create a script to extract the indicators throgh scripts rules , i want to scraw data throght the script rules define in the database

## llm rules
llm rule include the indicator, instruction, position,document_type


## script rules
scripts rule include the indicator, extract_rule, position,document_type






# task3 use skill-creator to create 5 skills in the project scope

## fd-cnreport-llm-rules-creator

- read the peace of the  document, generate rules automatically
- i want you create a python script to get the result , and save it to the skill scripts dir. use pydantic to make sure return the right structure data
- save it to the database define in the env file 
## fd-cnreport-pdf-llm-rules-creator

- generate the rules for the hole document, get every chapter
- i want you create a python script to seperate the documents through the outlooks and use llm to generate the rules , and save it to the current skill scripts dir. use pydantic to make sure return the right structure data
- save it to the database define in the env file 



## fd-cnreport-pdf-scripts-creator


- read the the rules define in the database.
- generate the scripts 
- save it to the database define in the env file 



## fd-cnreport-pdf-scripts-creator
- read the the hole type or document rules define in the database.
- generate the scripts form each rules target indicators
- save it to the database define in the env file 


## fd-cnreport-pdf-full-scripts-creator