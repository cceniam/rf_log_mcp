*** Test Cases ***
Passing Smoke
    Log    warm up

Single Failure
    Log    begin
    Fail    Expected 200 but got 503 from upstream
