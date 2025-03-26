echo "Test 1: Generate 10 samples from lumina_web.json"
python3 generator.py -f conf/gen/lumina_web.json -m 1 -n 10 -o conf/tar/stdout.json

echo "Test 2: Generate 10 samples from lumina_web.json with pattern"
python3 generator.py -f conf/gen/lumina_web.json -m 1 -n 10 -o conf/tar/stdout.json -p conf/pat/lumina_web_clf.txt

echo "Test 3: Generate 10 samples from lumina_web.json output to file"
python3 generator.py -f conf/gen/lumina_web.json -m 1 -n 10 -o conf/tar/file.json
mv test.json test_003.json
cat test_003.json

echo "Test 4: Generate 10 samples from lumina_web.json with pattern and output to file and print the file"
python3 generator.py -f conf/gen/lumina_web.json -m 1 -n 10 -o conf/tar/file.json -p conf/pat/lumina_web_clf.txt
mv test.json test_004.json
cat test_004.json

echo "Test 5: Generate ten minutes worth of data to a file from clickstream.json using simulated clock"
python3 generator.py -f conf/gen/clickstream.json -o conf/tar/file.json -t 10m -s "2027-03-12" -m 2
mv test.json test_005.json
cat test_005.json

echo "WARN: Tests for other targets not currently available."
