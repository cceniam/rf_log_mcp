*** Settings ***
Library    DoesNotExist

*** Keywords ***
Create Long Failure
    ${long}=    Evaluate    "retry evidence " * 80
    Fail    ${long}

*** Test Cases ***
Long Failure
    Log    collected line one
    Log    collected line two
    Log    collected line three
    Log    collected line four
    Log    collected line five
    Log    collected line six
    Log    collected line seven
    Log    collected line eight
    Log    collected line nine
    Log    collected line ten
    Log    collected line eleven
    Log    collected line twelve
    Create Long Failure

Secondary Failure
    Fail    secondary failure
