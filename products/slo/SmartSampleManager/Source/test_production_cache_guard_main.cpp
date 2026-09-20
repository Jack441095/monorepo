#include <iostream>
#include <sys/wait.h>
#include <unistd.h>

#include "SampleManagerEngine.h"

// Verifies the test-binary guard aborts before SQLite can open the real
// production cache. The child intentionally has no test override; the parent
// only observes its expected failure and confirms the DB metadata is unchanged.
int main()
{
    const auto productionDb = SampleManagerEngine::getCacheDbFile();
    const bool existedBefore = productionDb.existsAsFile();
    const auto sizeBefore = existedBefore ? productionDb.getSize() : -1;
    const auto modifiedBefore = existedBefore ? productionDb.getLastModificationTime()
                                              : juce::Time();

    const pid_t child = fork();
    if (child < 0) {
        std::cerr << "FAIL: could not create production-cache guard probe" << std::endl;
        return 1;
    }
    if (child == 0) {
        SampleManagerEngine engine;
        juce::ignoreUnused(engine);
        _exit(0); // Reaching this means the guard failed open.
    }

    int status = 0;
    if (waitpid(child, &status, 0) != child || !WIFSIGNALED(status)) {
        std::cerr << "FAIL: production-cache guard did not fail closed" << std::endl;
        return 1;
    }

    const bool existsAfter = productionDb.existsAsFile();
    if (existedBefore != existsAfter
        || (existedBefore && (sizeBefore != productionDb.getSize()
                              || modifiedBefore != productionDb.getLastModificationTime()))) {
        std::cerr << "FAIL: production cache changed during guard probe" << std::endl;
        return 1;
    }

    std::cout << "PASS: production cache guard aborted before opening the DB" << std::endl;
    return 0;
}
