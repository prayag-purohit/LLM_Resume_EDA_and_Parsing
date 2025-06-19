This is a prompt for our validator model, that will analyze the response, and refine it until there is no information missing

```
You will be given a response from a model that is parsing a resume in a specific format. You have to validate whether there are any problems in the parsing.

- The response should be in a valid JSON format
- The response should not contain any special characters like new line characters
- The response should have dates in place for dates. Should not be 'present'. If 'present' then use 01-01-2025 as a placeholder (keep the format of the data consistent with rest of the resume)
- Check if the skill sections is correctly been classified with soft skills, and technical skills.
- If there are components missed by the previous model. You can add a new key called 'missed_sections', and the text with appropriate top level keys.

Do not hallucinate, and output only JSON object. The response you provide, will directly be added to a mongodb database.  

```