*** Keywords ***
Outer Step
    Log    entering outer
    Inner Step

Inner Step
    Log    before failure
    Fail    Nested keyword failure

*** Test Cases ***
Nested Failure
    Outer Step
