"""Actual queued lambda/guard with a host queue; not guest RS scheduling proof."""
import unittest

from test_rs_transaction_validation import RS, run_sanitized


class RsSingleFrameDispatchTests(unittest.TestCase):
    def test_actual_sfc_predicate_rejects_invalid_pid_and_other_commands(self):
        guard = RS.REPLACEMENTS[RS.TRANSACTION][-1][1]
        source = r'''#include <cassert>
enum class RSCommandType { CANVAS_NODE,OTHER };
enum class RSCanvasNodeCommandType { CANVAS_NODE_UPDATE_RECORDING,OTHER };
struct Command {
    bool valid;
    RSCommandType type;
    RSCanvasNodeCommandType subType;
    int processed=0;
    bool IsCallingPidValid() const { return valid; }
    RSCommandType GetType() const { return type; }
    RSCanvasNodeCommandType GetSubType() const { return subType; }
    void Process(int&) { ++processed; }
};
void Process(Command* command,int& context) {
''' + guard + r'''            command->GetSubType() == RSCanvasNodeCommandType::CANVAS_NODE_UPDATE_RECORDING) {
            command->Process(context);
        }
}
int main() {
    int context=0;Process(nullptr,context);
    for(bool valid:{false,true}) for(auto type:{RSCommandType::CANVAS_NODE,RSCommandType::OTHER})
        for(auto subType:{RSCanvasNodeCommandType::CANVAS_NODE_UPDATE_RECORDING,RSCanvasNodeCommandType::OTHER}) {
            Command command{valid,type,subType};Process(&command,context);
            assert(command.processed==static_cast<int>(valid && type==RSCommandType::CANVAS_NODE &&
                subType==RSCanvasNodeCommandType::CANVAS_NODE_UPDATE_RECORDING));
        }
}
'''
        run_sanitized('#include <initializer_list>\n' + source)


if __name__ == '__main__':
    unittest.main()
