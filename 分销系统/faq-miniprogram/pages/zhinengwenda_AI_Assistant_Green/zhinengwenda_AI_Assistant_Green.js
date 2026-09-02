const app = getApp();
const { calculateFeedbackModalOffset } = require('./feedbackModalLayout');
const {
  buildChatSessionStorageKey,
  serializeChatSessionState,
  deserializeChatSessionState
} = require('./chatSessionCache');
const DEEP_THINKING_DELAY = 10000;
const DEEP_THINKING_TEXT = '正在进行深度思考，请稍候...';
const VOICE_RECOGNITION_MAX_DURATION = 30000;
const FEEDBACK_MODAL_SAFE_GAP = 16;
const DEFAULT_FEEDBACK_MODAL_STYLE = 'transform: translateY(0px);';
const AGENT_NETWORK_ERROR_TEXT = '网络错误，请重试';
const AGENT_ERROR_MARKERS = [
  'run workflow failed',
  'query request failed',
  'responsemetadata',
  'agent 执行出错',
  '工具未授权',
  '入参错误',
  '网络异常',
  'status: failed'
];

let wechatSIPlugin = null;
try {
  if (typeof requirePlugin === 'function') {
    wechatSIPlugin = requirePlugin('WechatSI');
  }
} catch (err) {
  console.warn('WechatSI plugin unavailable:', err);
}

function formatGuideSeriesLabel(value) {
  return String(value || '').replace(/I-LINE-/g, 'I-Line ');
}

function normalizeAgentReplyText(value) {
  const text = String(value || '');
  const lowered = text.toLowerCase();
  return AGENT_ERROR_MARKERS.some((marker) => lowered.includes(marker))
    ? AGENT_NETWORK_ERROR_TEXT
    : text;
}

function formatGuideAnswerText(value) {
  const source = String(value || '');
  if (!source) {
    return '';
  }

  const markdownTokenRegex = /!?\[[^\]]*\]\((?:<[^>]+>|[^)]+)\)/g;
  let result = '';
  let lastIndex = 0;
  let match;

  while ((match = markdownTokenRegex.exec(source)) !== null) {
    result += formatGuideSeriesLabel(source.slice(lastIndex, match.index));
    result += match[0];
    lastIndex = match.index + match[0].length;
  }

  result += formatGuideSeriesLabel(source.slice(lastIndex));
  return result;
}

function isCanalisGuideNode(node) {
  if (!node || typeof node !== 'object') {
    return false;
  }

  const id = String(node.id || '').trim().toLowerCase();
  const label = String(node.label || '').trim().toLowerCase();
  return id === 'canalis' || label === 'canalis';
}

function normalizeGuideTreeContent(node, parentKey = '') {
  if (Array.isArray(node)) {
    return node
      .map((item) => normalizeGuideTreeContent(item, parentKey))
      .filter(Boolean);
  }

  if (!node || typeof node !== 'object') {
    return node;
  }

  if (isCanalisGuideNode(node)) {
    return null;
  }

  const normalizedNode = {};
  const displayKeys = new Set(['label', 'title', 'hint', 'answer_text']);
  Object.keys(node).forEach((key) => {
    const value = node[key];
    if (typeof value === 'string') {
      if (key === 'answer') {
        normalizedNode[key] = formatGuideAnswerText(value);
      } else if (displayKeys.has(key)) {
        normalizedNode[key] = formatGuideSeriesLabel(value);
      } else {
        normalizedNode[key] = value;
      }
      return;
    }

    if (Array.isArray(value)) {
      normalizedNode[key] = value
        .map((item) => normalizeGuideTreeContent(item, key))
        .filter(Boolean);
      return;
    }

    if (value && typeof value === 'object') {
      normalizedNode[key] = normalizeGuideTreeContent(value, key);
      return;
    }

    normalizedNode[key] = value;
  });

  return normalizedNode;
}

function createLeafNode(id, label, answer) {
  return {
    id,
    label,
    answer
  };
}

function createPendingSectionNode(pathText, id, label) {
  return createLeafNode(
    id,
    label,
    `${pathText} / ${label}\n内容正在整理中，后续会补充为正式资料。`
  );
}

function createPendingProductNode(id, label) {
  return {
    id,
    label,
    children: [
      createLeafNode(
        `${id}-pending`,
        '内容建设中',
        `${label}\n这个产品的快捷导航正在整理中，后续会继续补充。`
      )
    ]
  };
}

const PRODUCT_GUIDE_TREE = {
  id: 'root',
  label: '产品选择',
  title: '常见问题快速导航',
  hint: '请先选择具体产品，再逐级点击到你想咨询的问题。',
  layout: 'grid',
  children: [
    {
      id: 'iline-b',
      label: 'I-LINE-B',
      children: [
        createPendingSectionNode('I-LINE-B', 'iline-b-overview', '参数概览'),
        createLeafNode(
          'iline-b-selection',
          '选型指引',
          'I-LINE-B / 选型指引\n1. 先确认项目场景和额定电流。\n2. 再确认安装环境、转角数量和分接需求。\n3. 这条内容后面也可以接成正式选型说明。'
        ),
        createLeafNode(
          'iline-b-product-image',
          '产品概览图',
          'I-LINE-B / 产品概览图\n这里后续可以配置产品概览图，也可以改成图片型答案。'
        ),
        {
          id: 'iline-b-model-rules',
          label: '型号编制规则',
          children: [
            createPendingSectionNode('I-LINE-B / 型号编制规则', 'iline-b-busbar-code', '母线编号规则'),
            createPendingSectionNode(
              'I-LINE-B / 型号编制规则',
              'iline-b-plug-in-box',
              '施耐德电气插接箱（16A-800A）'
            ),
            createPendingSectionNode(
              'I-LINE-B / 型号编制规则',
              'iline-b-side-box',
              '施耐德电气插接箱侧操箱（16A-250A）'
            ),
            createPendingSectionNode(
              'I-LINE-B / 型号编制规则',
              'iline-b-compact-ns-box',
              '施耐德电气Compact NS断路器插接箱 (1000A-1600A)'
            ),
            createPendingSectionNode(
              'I-LINE-B / 型号编制规则',
              'iline-b-ezd-box',
              '施耐德电气EZD断路器插接箱 (15A－100A)'
            )
          ]
        },
        {
          id: 'iline-b-product-model',
          label: '产品型号',
          layout: 'compact',
          children: [
            {
              id: 'iline-b-common-models',
              label: '常用产品型号(800A-6300A)',
              children: [
                createPendingSectionNode(
                  'I-LINE-B / 产品型号 / 常用产品型号(800A-6300A)',
                  'iline-b-common-connector',
                  '连接头'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 产品型号 / 常用产品型号(800A-6300A)',
                  'iline-b-common-feed-unit',
                  '馈电单元'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 产品型号 / 常用产品型号(800A-6300A)',
                  'iline-b-common-elbow',
                  '弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 产品型号 / 常用产品型号(800A-6300A)',
                  'iline-b-common-special-part',
                  '特殊部件'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 产品型号 / 常用产品型号(800A-6300A)',
                  'iline-b-common-terminal-end',
                  '终端封'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 产品型号 / 常用产品型号(800A-6300A)',
                  'iline-b-common-hanger',
                  '安装吊架'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 产品型号 / 常用产品型号(800A-6300A)',
                  'iline-b-common-wall-flange',
                  '穿墙法兰'
                )
              ]
            },
            createPendingSectionNode(
              'I-LINE-B / 产品型号',
              'iline-b-nsx-common-model',
              '施耐德电气ComPacT NSX断路器插接箱常用型号（16A-500A）'
            ),
            createPendingSectionNode(
              'I-LINE-B / 产品型号',
              'iline-b-cvs-common-model',
              '施耐德电气EasyPact CVS断路器插接箱常用型号（16A-500A）'
            ),
            createPendingSectionNode(
              'I-LINE-B / 产品型号',
              'iline-b-ezd-common-model',
              '施耐德电气Compact EZD断路器插接箱常用型号(15A-100A)'
            ),
            createPendingSectionNode(
              'I-LINE-B / 产品型号',
              'iline-b-nsx-box',
              '施耐德电气ComPacT NSX断路器插接箱（16-250A）'
            ),
            createPendingSectionNode(
              'I-LINE-B / 产品型号',
              'iline-b-cvs-box',
              '施耐德电气EasyPact CVS断路器插接箱（16-250A）'
            ),
            createPendingSectionNode(
              'I-LINE-B / 产品型号',
              'iline-b-compact-ns-model',
              '施耐德电气Compact NS断路器插接箱（630A-1600A）'
            )
          ]
        },
        {
          id: 'iline-b-size',
          label: '规格尺寸',
          layout: 'grid',
          children: [
            createPendingSectionNode('I-LINE-B / 规格尺寸', 'iline-b-straight-section', '直身段'),
            {
              id: 'iline-b-size-feed-unit',
              label: '馈电单元',
              children: [
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 馈电单元',
                  'iline-b-feed-unit-terminal-cable-box',
                  '电缆馈电箱（终端式）'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 馈电单元',
                  'iline-b-feed-unit-middle-cable-box',
                  '电缆馈电箱（中间式）'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 馈电单元',
                  'iline-b-feed-unit-standard-flange',
                  '标准法兰'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 馈电单元',
                  'iline-b-feed-unit-quick-flange',
                  '与配电柜连接的快接法兰'
                )
              ]
            },
            {
              id: 'iline-b-turning-part',
              label: '转向部件',
              children: [
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 转向部件',
                  'iline-b-horizontal-elbow',
                  '水平弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 转向部件',
                  'iline-b-turning-t',
                  'T接'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 转向部件',
                  'iline-b-vertical-elbow',
                  '立式弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 转向部件',
                  'iline-b-combined-elbow',
                  '组合弯头'
                )
              ]
            },
            {
              id: 'iline-b-size-special-part',
              label: '特殊部件',
              children: [
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 特殊部件',
                  'iline-b-fuse-free-taper-joint',
                  '无熔丝变容节'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 特殊部件',
                  'iline-b-expansion-joint',
                  '膨胀节'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 特殊部件',
                  'iline-b-size-terminal-end',
                  '终端封'
                )
              ]
            },
            {
              id: 'iline-b-size-hanger',
              label: '安装吊架',
              children: [
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 安装吊架',
                  'iline-b-flat-hanger',
                  '平面吊架'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 安装吊架',
                  'iline-b-vertical-hanger',
                  '立式吊架'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 安装吊架',
                  'iline-b-vertical-fixed-bracket',
                  '垂直固定式支架'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 安装吊架',
                  'iline-b-vertical-spring-bracket',
                  '垂直弹簧式支架'
                )
              ]
            },
            {
              id: 'iline-b-accessories',
              label: '附件',
              children: [
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 附件',
                  'iline-b-size-wall-flange',
                  '穿墙法兰'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 附件',
                  'iline-b-soft-connector',
                  '软连接'
                )
              ]
            },
            {
              id: 'iline-b-breaker-box',
              label: '配施耐德电气断路器插接箱',
              children: [
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-b-breaker-box-side-16-250a',
                  '16-250A插接箱（侧操）'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-b-breaker-box-16-250a',
                  '16-250A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-b-breaker-box-252-500a',
                  '252-500A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-b-breaker-box-630a',
                  '630A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-b-breaker-box-800a',
                  '800A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-B / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-b-breaker-box-1000-1600a',
                  '1000-1600A插接箱'
                )
              ]
            }
          ]
        }
      ]
    },
    {
      id: 'iline-c',
      label: 'I-LINE-C',
      children: [
        createPendingSectionNode('I-LINE-C', 'iline-c-product-image', '产品概览图'),
        createPendingSectionNode('I-LINE-C', 'iline-c-parameter-overview', '参数概览'),
        createPendingSectionNode('I-LINE-C', 'iline-c-selection-guide', '选型指引'),
        {
          id: 'iline-c-model-rules',
          label: '型号编制规则',
          layout: 'compact',
          children: [
            createPendingSectionNode('I-LINE-C / 型号编制规则', 'iline-c-copper-busbar', '铜母线'),
            createPendingSectionNode(
              'I-LINE-C / 型号编制规则',
              'iline-c-plug-in-box',
              '施耐德电气插接箱（16-800A）'
            ),
            createPendingSectionNode(
              'I-LINE-C / 型号编制规则',
              'iline-c-side-box',
              '施耐德电气插接箱侧操箱（16-250A）'
            ),
            createPendingSectionNode(
              'I-LINE-C / 型号编制规则',
              'iline-c-compact-ns-box',
              '施耐德电气Compact NS断路器插接箱（1000-1600A）'
            ),
            createPendingSectionNode(
              'I-LINE-C / 型号编制规则',
              'iline-c-ezd-box',
              '施耐德电气EZD断路器插接箱（15-100A）'
            )
          ]
        },
        {
          id: 'iline-c-product-model',
          label: '产品型号',
          layout: 'compact',
          children: [
            {
              id: 'iline-c-common-models-630-2500-group',
              label: '常用产品型号（630-2500A）',
              children: [
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-c-common-630-2500-connector',
                  '连接头'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-c-common-630-2500-feed-unit',
                  '馈电单元'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-c-common-630-2500-flange',
                  '法兰'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-c-common-630-2500-elbow',
                  '弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-c-common-630-2500-mounting-bracket',
                  '安装支架'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-c-common-630-2500-terminal-end',
                  '终端封'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-c-common-630-2500-special-part',
                  '特殊部件'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-c-common-630-2500-accessories',
                  '附件'
                )
              ]
            },
            {
              id: 'iline-c-common-models-3000-6000-group',
              label: '常用产品型号（3000-6000A）',
              children: [
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（3000-6000A）',
                  'iline-c-common-3000-6000-feed-unit',
                  '馈电单元'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（3000-6000A）',
                  'iline-c-common-3000-6000-flange',
                  '法兰'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（3000-6000A）',
                  'iline-c-common-3000-6000-elbow',
                  '弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（3000-6000A）',
                  'iline-c-common-3000-6000-mounting-bracket',
                  '安装支架'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（3000-6000A）',
                  'iline-c-common-3000-6000-terminal-end',
                  '终端封'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（3000-6000A）',
                  'iline-c-common-3000-6000-special-part',
                  '特殊部件'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 产品型号 / 常用产品型号（3000-6000A）',
                  'iline-c-common-3000-6000-accessories',
                  '附件'
                )
              ]
            },
            createPendingSectionNode(
              'I-LINE-C / 产品型号',
              'iline-c-nsx-common-model',
              'ComPacT NSX断路器插接箱常用型号（16-500A）'
            ),
            createPendingSectionNode(
              'I-LINE-C / 产品型号',
              'iline-c-cvs-common-model',
              'EasyPact CVS断路器插接箱常用型号（16-500A）'
            ),
            createPendingSectionNode(
              'I-LINE-C / 产品型号',
              'iline-c-ezd-common-model',
              'Compact EZD断路器插接箱常用型号（15-100A）'
            ),
            createPendingSectionNode(
              'I-LINE-C / 产品型号',
              'iline-c-nsx-box',
              'ComPacT NSX断路器插接箱（16-250A）'
            ),
            createPendingSectionNode(
              'I-LINE-C / 产品型号',
              'iline-c-cvs-box',
              'EasyPact CVS断路器插接箱（16-250A）'
            ),
            createPendingSectionNode(
              'I-LINE-C / 产品型号',
              'iline-c-compact-ns-model',
              'Compact NS断路器插接箱（630A-1600A）'
            )
          ]
        },
        {
          id: 'iline-c-size',
          label: '规格尺寸',
          layout: 'grid',
          children: [
            createPendingSectionNode('I-LINE-C / 规格尺寸', 'iline-c-straight-section', '直身段'),
            {
              id: 'iline-c-feed-unit-etbe',
              label: '馈电单元（ETBE）',
              children: [
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 馈电单元（ETBE）',
                  'iline-c-etbe-cable-terminal',
                  '电缆馈电箱-终端式'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 馈电单元（ETBE）',
                  'iline-c-etbe-cable-middle',
                  '电缆馈电箱-中间式'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 馈电单元（ETBE）',
                  'iline-c-etbe-transformer-flange',
                  '变压器连接法兰'
                )
              ]
            },
            {
              id: 'iline-c-feed-unit-fer',
              label: '馈电单元（FER）',
              children: [
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 馈电单元（FER）',
                  'iline-c-fer-standard-flange',
                  '标准法兰'
                )
              ]
            },
            {
              id: 'iline-c-feed-unit-qf',
              label: '馈电单元（QF）',
              children: [
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 馈电单元（QF）',
                  'iline-c-qf-quick-flange',
                  '与配电柜连接的快接法兰'
                )
              ]
            },
            {
              id: 'iline-c-turning-part',
              label: '转向部件',
              children: [
                createPendingSectionNode('I-LINE-C / 规格尺寸 / 转向部件', 'iline-c-turning-t', 'T接'),
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 转向部件',
                  'iline-c-horizontal-elbow',
                  '水平弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 转向部件',
                  'iline-c-vertical-elbow',
                  '立式弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 转向部件',
                  'iline-c-combined-elbow',
                  '组合弯头'
                )
              ]
            },
            {
              id: 'iline-c-special-part',
              label: '特殊部件',
              children: [
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 特殊部件',
                  'iline-c-taper-joint',
                  '无熔丝变容节'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 特殊部件',
                  'iline-c-expansion-joint-ej',
                  '膨胀节（只提供户内型）（EJ）'
                )
              ]
            },
            {
              id: 'iline-c-accessories',
              label: '附件',
              children: [
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 附件',
                  'iline-c-wall-flange',
                  '穿墙法兰'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 附件',
                  'iline-c-terminal-end',
                  '终端封'
                )
              ]
            },
            {
              id: 'iline-c-install-hanger',
              label: '安装吊架',
              children: [
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 安装吊架',
                  'iline-c-flat-hanger',
                  '平面吊架'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 安装吊架',
                  'iline-c-vertical-hanger',
                  '立式吊架'
                )
              ]
            },
            {
              id: 'iline-c-vertical-bracket',
              label: '垂直安装用支架',
              children: [
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 垂直安装用支架',
                  'iline-c-vertical-fixed-bracket',
                  '垂直固定式支架'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 垂直安装用支架',
                  'iline-c-vertical-spring-bracket',
                  '垂直弹簧式支架'
                )
              ]
            },
            {
              id: 'iline-c-breaker-box',
              label: '配施耐德电气断路器插接箱',
              children: [
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-c-side-box-16-250',
                  '16-250A插接箱（侧操）'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-c-box-16-250',
                  '16-250A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-c-box-252-500',
                  '252-500A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-c-box-630',
                  '630A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-c-box-800',
                  '800A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-C / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-c-box-1000-1600',
                  '1000-1600A插接箱'
                )
              ]
            }
          ]
        }
      ]
    },
    {
      id: 'iline-d',
      label: 'I-LINE-D',
      children: [
        createPendingSectionNode('I-LINE-D', 'iline-d-product-image', '产品概览图'),
        createPendingSectionNode('I-LINE-D', 'iline-d-parameter-overview', '参数概览'),
        createPendingSectionNode('I-LINE-D', 'iline-d-selection-guide', '选型指引'),
        {
          id: 'iline-d-model-rules',
          label: '型号编制规则',
          layout: 'compact',
          children: [
            createPendingSectionNode('I-LINE-D / 型号编制规则', 'iline-d-copper-busbar', '铜母线'),
            createPendingSectionNode(
              'I-LINE-D / 型号编制规则',
              'iline-d-plug-in-box',
              '施耐德电气插接箱（16A-800A）'
            ),
            createPendingSectionNode(
              'I-LINE-D / 型号编制规则',
              'iline-d-side-box',
              '施耐德电气插接箱侧操箱（16-250A）'
            ),
            createPendingSectionNode(
              'I-LINE-D / 型号编制规则',
              'iline-d-compact-ns-box',
              '施耐德电气Compact NS断路器插接箱（1000-1600A）'
            ),
            createPendingSectionNode(
              'I-LINE-D / 型号编制规则',
              'iline-d-ezd-box',
              '施耐德电气EZD断路器插接箱（15-100A）'
            )
          ]
        },
        {
          id: 'iline-d-product-model',
          label: '产品型号',
          layout: 'compact',
          children: [
            {
              id: 'iline-d-common-models-630-2500-group',
              label: '常用产品型号（630-2500A）',
              children: [
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-d-common-630-2500-connector',
                  '连接头'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-d-common-630-2500-feed-unit',
                  '馈电单元'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-d-common-630-2500-flange',
                  '法兰'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-d-common-630-2500-elbow',
                  '弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-d-common-630-2500-mounting-bracket',
                  '安装支架'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-d-common-630-2500-terminal-end',
                  '终端封'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-d-common-630-2500-special-part',
                  '特殊部件'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（630-2500A）',
                  'iline-d-common-630-2500-accessories',
                  '附件'
                )
              ]
            },
            {
              id: 'iline-d-common-models-3200-6300-group',
              label: '常用产品型号（3200-6300A）',
              children: [
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（3200-6300A）',
                  'iline-d-common-3200-6300-feed-unit',
                  '馈电单元'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（3200-6300A）',
                  'iline-d-common-3200-6300-flange',
                  '法兰'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（3200-6300A）',
                  'iline-d-common-3200-6300-elbow',
                  '弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（3200-6300A）',
                  'iline-d-common-3200-6300-mounting-bracket',
                  '安装支架'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（3200-6300A）',
                  'iline-d-common-3200-6300-terminal-end',
                  '终端封'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（3200-6300A）',
                  'iline-d-common-3200-6300-special-part',
                  '特殊部件'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 产品型号 / 常用产品型号（3200-6300A）',
                  'iline-d-common-3200-6300-accessories',
                  '附件'
                )
              ]
            },
            createPendingSectionNode(
              'I-LINE-D / 产品型号',
              'iline-d-nsx-common-model',
              'ComPacT NSX断路器插接箱常用型号（16-500A）'
            ),
            createPendingSectionNode(
              'I-LINE-D / 产品型号',
              'iline-d-cvs-common-model',
              'EasyPact CVS 断路器插接箱常用型号（16-500A）'
            ),
            createPendingSectionNode(
              'I-LINE-D / 产品型号',
              'iline-d-ezd-common-model',
              'Compact EZD断路器插接箱常用型号（15-100A）'
            ),
            createPendingSectionNode(
              'I-LINE-D / 产品型号',
              'iline-d-nsx-box',
              'ComPacT NSX断路器插接箱（16-250A）'
            ),
            createPendingSectionNode(
              'I-LINE-D / 产品型号',
              'iline-d-cvs-box',
              'EasyPact CVS断路器插接箱（16-250A）'
            ),
            createPendingSectionNode(
              'I-LINE-D / 产品型号',
              'iline-d-compact-ns-model',
              'Compact NS断路器插接箱（630A-1600A）'
            )
          ]
        },
        {
          id: 'iline-d-size',
          label: '规格尺寸',
          layout: 'grid',
          children: [
            createPendingSectionNode('I-LINE-D / 规格尺寸', 'iline-d-straight-section', '直身段'),
            {
              id: 'iline-d-feed-unit-etbe',
              label: '馈电单元（ETBE）',
              children: [
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 馈电单元（ETBE）',
                  'iline-d-etbe-cable-terminal',
                  '电缆馈电箱-终端式'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 馈电单元（ETBE）',
                  'iline-d-etbe-cable-middle',
                  '电缆馈电箱-中间式'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 馈电单元（ETBE）',
                  'iline-d-etbe-transformer-flange',
                  '变压器连接法兰'
                )
              ]
            },
            {
              id: 'iline-d-feed-unit-fe',
              label: '馈电单元（FE）',
              children: [
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 馈电单元（FE）',
                  'iline-d-fe-standard-flange',
                  '标准法兰'
                )
              ]
            },
            {
              id: 'iline-d-feed-unit-qf',
              label: '馈电单元（QF）',
              children: [
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 馈电单元（QF）',
                  'iline-d-qf-quick-flange',
                  '与配电柜连接的快接法兰'
                )
              ]
            },
            {
              id: 'iline-d-turning-part',
              label: '转向部件',
              children: [
                createPendingSectionNode('I-LINE-D / 规格尺寸 / 转向部件', 'iline-d-turning-t', 'T接'),
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 转向部件',
                  'iline-d-horizontal-elbow',
                  '水平弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 转向部件',
                  'iline-d-vertical-elbow',
                  '立式弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 转向部件',
                  'iline-d-combined-elbow',
                  '组合弯头'
                )
              ]
            },
            {
              id: 'iline-d-special-part',
              label: '特殊部件',
              children: [
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 特殊部件',
                  'iline-d-taper-joint',
                  '无熔丝变容节'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 特殊部件',
                  'iline-d-expansion-joint-ej',
                  '膨胀节（只提供户内型）（EJ）'
                )
              ]
            },
            {
              id: 'iline-d-accessories',
              label: '附件',
              children: [
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 附件',
                  'iline-d-wall-flange',
                  '穿墙法兰'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 附件',
                  'iline-d-terminal-end',
                  '终端封'
                )
              ]
            },
            {
              id: 'iline-d-install-hanger',
              label: '安装吊架',
              children: [
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 安装吊架',
                  'iline-d-flat-hanger',
                  '平面吊架'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 安装吊架',
                  'iline-d-vertical-hanger',
                  '立式吊架'
                )
              ]
            },
            {
              id: 'iline-d-vertical-bracket',
              label: '垂直安装用支架',
              children: [
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 垂直安装用支架',
                  'iline-d-vertical-fixed-bracket',
                  '垂直固定式支架'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 垂直安装用支架',
                  'iline-d-vertical-spring-bracket',
                  '垂直弹簧式支架'
                )
              ]
            },
            {
              id: 'iline-d-breaker-box',
              label: '配施耐德电气断路器插接箱',
              children: [
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-d-side-box-16-250',
                  '16-250A插接箱（侧操）'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-d-box-16-250',
                  '16-250A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-d-box-252-500',
                  '252-500A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-d-box-630',
                  '630A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-d-box-800',
                  '800A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-D / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-d-box-1000-1600',
                  '1000-1600A插接箱'
                )
              ]
            }
          ]
        }
      ]
    },
    {
      id: 'iline-h',
      label: 'I-LINE-H',
      children: [
        createPendingSectionNode('I-LINE-H', 'iline-h-product-image', '产品概览图'),
        createPendingSectionNode('I-LINE-H', 'iline-h-parameter-overview', '参数概览'),
        createPendingSectionNode('I-LINE-H', 'iline-h-selection-guide', '选型指引'),
        {
          id: 'iline-h-model-rules',
          label: '型号编制规则',
          layout: 'compact',
          children: [
            createPendingSectionNode('I-LINE-H / 型号编制规则', 'iline-h-copper-busbar', '铜母线'),
            createPendingSectionNode(
              'I-LINE-H / 型号编制规则',
              'iline-h-plug-interface-naming',
              '插接口命名规则'
            ),
            createPendingSectionNode(
              'I-LINE-H / 型号编制规则',
              'iline-h-plug-in-box-16-500',
              '施耐德电气插接箱（16-500A）'
            ),
            createPendingSectionNode(
              'I-LINE-H / 型号编制规则',
              'iline-h-plug-in-box-630-1250',
              '施耐德电气插接箱（630-1250A）'
            ),
            createPendingSectionNode(
              'I-LINE-H / 型号编制规则',
              'iline-h-plug-in-box-1600',
              '施耐德电气插接箱（1600A）'
            )
          ]
        },
        {
          id: 'iline-h-product-model',
          label: '产品型号',
          layout: 'compact',
          children: [
            {
              id: 'iline-h-common-models-400-5000-group',
              label: '常用产品型号（400-5000A）',
              children: [
                createPendingSectionNode(
                  'I-LINE-H / 产品型号 / 常用产品型号（400-5000A）',
                  'iline-h-common-400-5000-connector',
                  '连接头'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 产品型号 / 常用产品型号（400-5000A）',
                  'iline-h-common-400-5000-feed-unit',
                  '馈电单元'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 产品型号 / 常用产品型号（400-5000A）',
                  'iline-h-common-400-5000-elbow',
                  '弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 产品型号 / 常用产品型号（400-5000A）',
                  'iline-h-common-400-5000-mounting-bracket',
                  '安装支架'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 产品型号 / 常用产品型号（400-5000A）',
                  'iline-h-common-400-5000-terminal-end',
                  '终端封'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 产品型号 / 常用产品型号（400-5000A）',
                  'iline-h-common-400-5000-special-part',
                  '特殊部件'
                )
              ]
            },
            createPendingSectionNode(
              'I-LINE-H / 产品型号',
              'iline-h-nsx-common-model',
              'ComPacT NSX断路器插接箱常用型号（16-500A）'
            ),
            createPendingSectionNode(
              'I-LINE-H / 产品型号',
              'iline-h-cvs-common-model',
              'Compact CVS断路器插接箱常用型号（16-500A）'
            ),
            createPendingSectionNode(
              'I-LINE-H / 产品型号',
              'iline-h-easypact-common-model',
              'Easypact断路器插接箱常用型号（16-100A）'
            ),
            createPendingSectionNode(
              'I-LINE-H / 产品型号',
              'iline-h-compact-common-model',
              'Compact断路器插接箱常用型号（630-1000A）'
            )
          ]
        },
        {
          id: 'iline-h-size',
          label: '规格尺寸',
          layout: 'grid',
          children: [
            createPendingSectionNode('I-LINE-H / 规格尺寸', 'iline-h-straight-section', '直身段'),
            {
              id: 'iline-h-feed-unit',
              label: '馈电单元',
              children: [
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 馈电单元',
                  'iline-h-feed-unit-cable-terminal',
                  '电缆馈电箱-终端式'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 馈电单元',
                  'iline-h-feed-unit-ctb',
                  '电缆馈电箱-CTB'
                )
              ]
            },
            {
              id: 'iline-h-feed-unit-fe',
              label: '馈电单元（FE）',
              children: [
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 馈电单元（FE）',
                  'iline-h-fe-standard-flange',
                  '标准法兰'
                )
              ]
            },
            {
              id: 'iline-h-turning-part',
              label: '转向部件',
              children: [
                createPendingSectionNode('I-LINE-H / 规格尺寸 / 转向部件', 'iline-h-turning-t', 'T接'),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 转向部件',
                  'iline-h-horizontal-elbow',
                  '水平弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 转向部件',
                  'iline-h-vertical-elbow',
                  '立式弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 转向部件',
                  'iline-h-combined-elbow',
                  '组合弯头'
                )
              ]
            },
            {
              id: 'iline-h-special-part',
              label: '特殊部件',
              children: [
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 特殊部件',
                  'iline-h-taper-joint',
                  '无熔丝变容节'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 特殊部件',
                  'iline-h-terminal-end',
                  '终端封'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 特殊部件',
                  'iline-h-expansion-joint',
                  '膨胀节'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 特殊部件',
                  'iline-h-phase-changer',
                  '换相器'
                )
              ]
            },
            {
              id: 'iline-h-accessories',
              label: '附件',
              children: [
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 附件',
                  'iline-h-wall-flange',
                  '穿墙法兰'
                )
              ]
            },
            {
              id: 'iline-h-install-hanger',
              label: '安装吊架',
              children: [
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 安装吊架',
                  'iline-h-horizontal-hanger',
                  '水平安装吊架'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 安装吊架',
                  'iline-h-vertical-hanger',
                  '立式吊架'
                )
              ]
            },
            {
              id: 'iline-h-vertical-bracket',
              label: '垂直安装用支架',
              children: [
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 垂直安装用支架',
                  'iline-h-vertical-fixed-bracket',
                  '垂直固定式支架'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 垂直安装用支架',
                  'iline-h-vertical-spring-bracket',
                  '垂直弹簧式支架'
                )
              ]
            },
            {
              id: 'iline-h-breaker-box',
              label: '配施耐德电气断路器插接箱',
              children: [
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-h-box-16-100-ezd',
                  '16-100A插接箱（EZD开关）'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-h-box-16-250-nsx-cvs',
                  '16-250A插接箱（NSX、CVS开关）'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-h-box-400-500',
                  '400-500A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-h-box-630-800',
                  '630-800A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-h-box-1000',
                  '1000A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-h-box-1250',
                  '1250A插接箱'
                ),
                createPendingSectionNode(
                  'I-LINE-H / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-h-box-1600',
                  '1600A插接箱'
                )
              ]
            }
          ]
        }
      ]
    },
    {
      id: 'iline-w-copper',
      label: 'I-LINE-W-铜',
      children: [
        createPendingSectionNode('I-LINE-W-铜', 'iline-w-copper-product-image', '产品概览图'),
        createPendingSectionNode('I-LINE-W-铜', 'iline-w-copper-parameter-overview', '参数概览'),
        createPendingSectionNode('I-LINE-W-铜', 'iline-w-copper-selection-guide', '选型指引'),
        {
          id: 'iline-w-copper-model-rules',
          label: '型号编制规则',
          layout: 'compact',
          children: [
            createPendingSectionNode('I-LINE-W-铜 / 型号编制规则', 'iline-w-copper-busbar', '母线'),
            createPendingSectionNode(
              'I-LINE-W-铜 / 型号编制规则',
              'iline-w-copper-nsx-cvs-box',
              '施耐德电气Compact NSX/CVS断路器插接箱（16A-500A）'
            ),
            createPendingSectionNode(
              'I-LINE-W-铜 / 型号编制规则',
              'iline-w-copper-nsx-box-630-800',
              '施耐德电气Compact NSX断路器插接箱（630A、800A）'
            )
          ]
        },
        {
          id: 'iline-w-copper-product-model',
          label: '产品型号',
          layout: 'compact',
          children: [
            {
              id: 'iline-w-copper-common-models-400-5000-group',
              label: '常用产品型号（400-5000A）',
              children: [
                createPendingSectionNode(
                  'I-LINE-W-铜 / 产品型号 / 常用产品型号（400-5000A）',
                  'iline-w-copper-common-feed-unit',
                  '馈电单元'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 产品型号 / 常用产品型号（400-5000A）',
                  'iline-w-copper-common-flange',
                  '法兰'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 产品型号 / 常用产品型号（400-5000A）',
                  'iline-w-copper-common-elbow',
                  '弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 产品型号 / 常用产品型号（400-5000A）',
                  'iline-w-copper-common-wall-flange',
                  '穿墙法兰'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 产品型号 / 常用产品型号（400-5000A）',
                  'iline-w-copper-common-mounting-bracket',
                  '安装支架'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 产品型号 / 常用产品型号（400-5000A）',
                  'iline-w-copper-common-terminal-end',
                  '终端封'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 产品型号 / 常用产品型号（400-5000A）',
                  'iline-w-copper-common-joint',
                  '接头'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 产品型号 / 常用产品型号（400-5000A）',
                  'iline-w-copper-common-special-part',
                  '特殊部件'
                )
              ]
            },
            createPendingSectionNode(
              'I-LINE-W-铜 / 产品型号',
              'iline-w-copper-nsx-plug-in-box',
              'Compact NSX 断路器插入式插接箱'
            ),
            createPendingSectionNode(
              'I-LINE-W-铜 / 产品型号',
              'iline-w-copper-cvs-plug-in-box',
              'Compact CVS 断路器插入式插接箱'
            ),
            createPendingSectionNode(
              'I-LINE-W-铜 / 产品型号',
              'iline-w-copper-large-fixed-box',
              '大型固定式插接箱'
            )
          ]
        },
        {
          id: 'iline-w-copper-size',
          label: '规格尺寸',
          layout: 'grid',
          children: [
            createPendingSectionNode('I-LINE-W-铜 / 规格尺寸', 'iline-w-copper-straight-section', '直身段'),
            {
              id: 'iline-w-copper-feed-unit-etb',
              label: '馈电单元（ETB）',
              children: [
                createPendingSectionNode(
                  'I-LINE-W-铜 / 规格尺寸 / 馈电单元（ETB）',
                  'iline-w-copper-etb-cable-terminal',
                  '电缆馈电箱-终端式'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 规格尺寸 / 馈电单元（ETB）',
                  'iline-w-copper-etb-terminal-end',
                  '终端封'
                )
              ]
            },
            {
              id: 'iline-w-copper-feed-unit-fe',
              label: '馈电单元（FE）',
              children: [
                createPendingSectionNode(
                  'I-LINE-W-铜 / 规格尺寸 / 馈电单元（FE）',
                  'iline-w-copper-fe-standard-flange',
                  '标准法兰'
                )
              ]
            },
            {
              id: 'iline-w-copper-turning-part',
              label: '转向部件',
              children: [
                createPendingSectionNode(
                  'I-LINE-W-铜 / 规格尺寸 / 转向部件',
                  'iline-w-copper-turning-t',
                  'T接'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 规格尺寸 / 转向部件',
                  'iline-w-copper-horizontal-elbow',
                  '水平弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 规格尺寸 / 转向部件',
                  'iline-w-copper-vertical-elbow',
                  '立式弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 规格尺寸 / 转向部件',
                  'iline-w-copper-combined-elbow',
                  '组合弯头'
                )
              ]
            },
            createPendingSectionNode('I-LINE-W-铜 / 规格尺寸', 'iline-w-copper-vertical-flange-elbow', '立式法兰弯头'),
            createPendingSectionNode('I-LINE-W-铜 / 规格尺寸', 'iline-w-copper-horizontal-flange-elbow', '水平法兰弯头'),
            createPendingSectionNode('I-LINE-W-铜 / 规格尺寸', 'iline-w-copper-taper-joint', '变容节'),
            createPendingSectionNode('I-LINE-W-铜 / 规格尺寸', 'iline-w-copper-expansion-joint', '膨胀节'),
            createPendingSectionNode('I-LINE-W-铜 / 规格尺寸', 'iline-w-copper-wall-flange', '穿墙法兰'),
            {
              id: 'iline-w-copper-install-hanger',
              label: '安装吊架',
              children: [
                createPendingSectionNode(
                  'I-LINE-W-铜 / 规格尺寸 / 安装吊架',
                  'iline-w-copper-flat-hanger',
                  '平面吊架'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 规格尺寸 / 安装吊架',
                  'iline-w-copper-vertical-hanger',
                  '立式吊架'
                )
              ]
            },
            {
              id: 'iline-w-copper-vertical-bracket',
              label: '垂直安装用支架',
              children: [
                createPendingSectionNode(
                  'I-LINE-W-铜 / 规格尺寸 / 垂直安装用支架',
                  'iline-w-copper-vertical-fixed-bracket',
                  '垂直固定式吊架'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 规格尺寸 / 垂直安装用支架',
                  'iline-w-copper-vertical-spring-bracket',
                  '垂直弹簧式支架'
                )
              ]
            },
            {
              id: 'iline-w-copper-breaker-box',
              label: '配施耐德电气断路器插接箱',
              children: [
                createPendingSectionNode(
                  'I-LINE-W-铜 / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-w-copper-box-16-250',
                  '16A-250A插接箱（NSX，CVS开关）'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-w-copper-box-400-500',
                  '400A-500A插接箱（NSX，CVS开关）'
                ),
                createPendingSectionNode(
                  'I-LINE-W-铜 / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-w-copper-box-630-800',
                  '630A-800A插接箱（NS开关）'
                )
              ]
            }
          ]
        }
      ]
    },
    {
      id: 'iline-w-alloy',
      label: 'I-LINE-W-合金',
      children: [
        createPendingSectionNode('I-LINE-W-合金', 'iline-w-alloy-product-image', '产品概览图'),
        {
          id: 'iline-w-alloy-model-rules',
          label: '型号编制规则',
          layout: 'compact',
          children: [
            createPendingSectionNode('I-LINE-W-合金 / 型号编制规则', 'iline-w-alloy-busbar', '母线'),
            createPendingSectionNode(
              'I-LINE-W-合金 / 型号编制规则',
              'iline-w-alloy-nsx-cvs-box',
              '施耐德电气Compact NSX/CVS断路器插接箱（16A-500A）'
            ),
            createPendingSectionNode(
              'I-LINE-W-合金 / 型号编制规则',
              'iline-w-alloy-nsx-cvs-box-module',
              '施耐德电气Compact NSX/CVS断路器插接盒（16A-500A）'
            )
          ]
        },
        {
          id: 'iline-w-alloy-product-model',
          label: '产品型号',
          layout: 'compact',
          children: [
            {
              id: 'iline-w-alloy-common-models-400-800-group',
              label: '常用产品型号（400-800A）',
              children: [
                createPendingSectionNode(
                  'I-LINE-W-合金 / 产品型号 / 常用产品型号（400-800A）',
                  'iline-w-alloy-common-feed-unit',
                  '馈电单元'
                ),
                createPendingSectionNode(
                  'I-LINE-W-合金 / 产品型号 / 常用产品型号（400-800A）',
                  'iline-w-alloy-common-flange',
                  '法兰'
                ),
                createPendingSectionNode(
                  'I-LINE-W-合金 / 产品型号 / 常用产品型号（400-800A）',
                  'iline-w-alloy-common-elbow',
                  '弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-W-合金 / 产品型号 / 常用产品型号（400-800A）',
                  'iline-w-alloy-common-wall-flange',
                  '穿墙法兰'
                ),
                createPendingSectionNode(
                  'I-LINE-W-合金 / 产品型号 / 常用产品型号（400-800A）',
                  'iline-w-alloy-common-mounting-bracket',
                  '安装支架'
                ),
                createPendingSectionNode(
                  'I-LINE-W-合金 / 产品型号 / 常用产品型号（400-800A）',
                  'iline-w-alloy-common-terminal-end',
                  '终端封'
                ),
                createPendingSectionNode(
                  'I-LINE-W-合金 / 产品型号 / 常用产品型号（400-800A）',
                  'iline-w-alloy-common-joint',
                  '接头'
                ),
                createPendingSectionNode(
                  'I-LINE-W-合金 / 产品型号 / 常用产品型号（400-800A）',
                  'iline-w-alloy-common-box-module',
                  '插接盒'
                )
              ]
            },
            createPendingSectionNode(
              'I-LINE-W-合金 / 产品型号',
              'iline-w-alloy-nsx-box',
              'Compact NSX 断路器插接箱（16A~500A）'
            ),
            createPendingSectionNode(
              'I-LINE-W-合金 / 产品型号',
              'iline-w-alloy-cvs-box',
              'Compact CVS 断路器插接箱（16A~500A）'
            )
          ]
        },
        {
          id: 'iline-w-alloy-size',
          label: '规格尺寸',
          layout: 'grid',
          children: [
            createPendingSectionNode('I-LINE-W-合金 / 规格尺寸', 'iline-w-alloy-straight-section', '直身段'),
            {
              id: 'iline-w-alloy-feed-unit-etb',
              label: '馈电单元（ETB）',
              children: [
                createPendingSectionNode(
                  'I-LINE-W-合金 / 规格尺寸 / 馈电单元（ETB）',
                  'iline-w-alloy-etb-cable-terminal',
                  '电缆馈电箱-终端式'
                )
              ]
            },
            {
              id: 'iline-w-alloy-feed-unit-fe',
              label: '馈电单元（FE）',
              children: [
                createPendingSectionNode(
                  'I-LINE-W-合金 / 规格尺寸 / 馈电单元（FE）',
                  'iline-w-alloy-fe-standard-flange',
                  '标准法兰'
                )
              ]
            },
            {
              id: 'iline-w-alloy-turning-part',
              label: '转向部件',
              children: [
                createPendingSectionNode(
                  'I-LINE-W-合金 / 规格尺寸 / 转向部件',
                  'iline-w-alloy-turning-t',
                  'T接'
                ),
                createPendingSectionNode(
                  'I-LINE-W-合金 / 规格尺寸 / 转向部件',
                  'iline-w-alloy-horizontal-elbow',
                  '水平弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-W-合金 / 规格尺寸 / 转向部件',
                  'iline-w-alloy-vertical-elbow',
                  '立式弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-W-合金 / 规格尺寸 / 转向部件',
                  'iline-w-alloy-combined-elbow',
                  '组合弯头'
                )
              ]
            },
            createPendingSectionNode('I-LINE-W-合金 / 规格尺寸', 'iline-w-alloy-vertical-flange-elbow', '立式法兰弯头'),
            createPendingSectionNode('I-LINE-W-合金 / 规格尺寸', 'iline-w-alloy-horizontal-flange-elbow', '水平法兰弯头'),
            createPendingSectionNode('I-LINE-W-合金 / 规格尺寸', 'iline-w-alloy-terminal-end', '终端封'),
            createPendingSectionNode('I-LINE-W-合金 / 规格尺寸', 'iline-w-alloy-wall-flange', '穿墙法兰'),
            {
              id: 'iline-w-alloy-install-hanger',
              label: '安装吊架',
              children: [
                createPendingSectionNode(
                  'I-LINE-W-合金 / 规格尺寸 / 安装吊架',
                  'iline-w-alloy-flat-hanger',
                  '平面吊架'
                ),
                createPendingSectionNode(
                  'I-LINE-W-合金 / 规格尺寸 / 安装吊架',
                  'iline-w-alloy-vertical-hanger',
                  '立式吊架'
                )
              ]
            },
            {
              id: 'iline-w-alloy-vertical-bracket',
              label: '垂直安装用支架',
              children: [
                createPendingSectionNode(
                  'I-LINE-W-合金 / 规格尺寸 / 垂直安装用支架',
                  'iline-w-alloy-vertical-fixed-bracket',
                  '垂直固定式支架'
                ),
                createPendingSectionNode(
                  'I-LINE-W-合金 / 规格尺寸 / 垂直安装用支架',
                  'iline-w-alloy-vertical-spring-bracket',
                  '垂直弹簧式支架'
                )
              ]
            },
            {
              id: 'iline-w-alloy-breaker-box',
              label: '配施耐德电气断路器插接箱',
              children: [
                createPendingSectionNode(
                  'I-LINE-W-合金 / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-w-alloy-box-16-250',
                  '16A-250A插接箱（NSX，CVS开关）'
                ),
                createPendingSectionNode(
                  'I-LINE-W-合金 / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-w-alloy-box-400-500',
                  '400A-500A插接箱（NSX，CVS开关）'
                )
              ]
            }
          ]
        }
      ]
    },
    {
      id: 'iline-v',
      label: 'I-LINE-V',
      children: [
        createPendingSectionNode('I-LINE-V', 'iline-v-product-image', '产品概览图'),
        createPendingSectionNode('I-LINE-V', 'iline-v-parameter-overview', '参数概览'),
        createPendingSectionNode('I-LINE-V', 'iline-v-selection-guide', '选型指引'),
        {
          id: 'iline-v-model-rules',
          label: '型号编制规则',
          layout: 'compact',
          children: [
            createPendingSectionNode('I-LINE-V / 型号编制规则', 'iline-v-busbar', '母线'),
            createPendingSectionNode(
              'I-LINE-V / 型号编制规则',
              'iline-v-connector-naming',
              '连接头编号规则'
            ),
            createPendingSectionNode(
              'I-LINE-V / 型号编制规则',
              'iline-v-connector-quote-model-rule',
              '连接头报价型号规则（插入式和固定式）'
            ),
            createPendingSectionNode(
              'I-LINE-V / 型号编制规则',
              'iline-v-nsx-cvs-box',
              '施耐德电气Compact NSX/CVS断路器插接箱（16A-500A）'
            ),
            createPendingSectionNode(
              'I-LINE-V / 型号编制规则',
              'iline-v-breaker-box',
              '施耐德电气断路器插接箱'
            )
          ]
        },
        {
          id: 'iline-v-product-model',
          label: '产品型号',
          layout: 'compact',
          children: [
            {
              id: 'iline-v-common-models-400-3200-group',
              label: '常用产品型号（400-3200A）',
              children: [
                createPendingSectionNode(
                  'I-LINE-V / 产品型号 / 常用产品型号（400-3200A）',
                  'iline-v-common-400-3200-feed-unit',
                  '馈电单元'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 产品型号 / 常用产品型号（400-3200A）',
                  'iline-v-common-400-3200-flange',
                  '法兰'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 产品型号 / 常用产品型号（400-3200A）',
                  'iline-v-common-400-3200-elbow',
                  '弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 产品型号 / 常用产品型号（400-3200A）',
                  'iline-v-common-400-3200-connector',
                  '连接头'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 产品型号 / 常用产品型号（400-3200A）',
                  'iline-v-common-400-3200-mounting-bracket',
                  '安装支架'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 产品型号 / 常用产品型号（400-3200A）',
                  'iline-v-common-400-3200-terminal-end',
                  '终端封'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 产品型号 / 常用产品型号（400-3200A）',
                  'iline-v-common-400-3200-special-part',
                  '特殊部件'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 产品型号 / 常用产品型号（400-3200A）',
                  'iline-v-common-400-3200-accessories',
                  '附件'
                )
              ]
            },
            createPendingSectionNode(
              'I-LINE-V / 产品型号',
              'iline-v-nsx-plug-in-box',
              'Compact NSX断路器插入式插接箱'
            ),
            createPendingSectionNode(
              'I-LINE-V / 产品型号',
              'iline-v-nsx-fixed-box',
              'Compact NSX断路器固定式插接箱'
            ),
            createPendingSectionNode(
              'I-LINE-V / 产品型号',
              'iline-v-cvs-plug-in-box',
              'Compact CVS断路器插入式插接箱'
            ),
            createPendingSectionNode(
              'I-LINE-V / 产品型号',
              'iline-v-cvs-fixed-box',
              'Compact CVS断路器固定式插接箱'
            ),
            createPendingSectionNode(
              'I-LINE-V / 产品型号',
              'iline-v-easypact-plug-in-box',
              'Easypact断路器插入式插接箱（16A～100A）'
            )
          ]
        },
        {
          id: 'iline-v-size',
          label: '规格尺寸',
          layout: 'grid',
          children: [
            createPendingSectionNode('I-LINE-V / 规格尺寸', 'iline-v-straight-section', '直身段'),
            createPendingSectionNode('I-LINE-V / 规格尺寸', 'iline-v-plug-in-connector', '插入式连接头'),
            createPendingSectionNode('I-LINE-V / 规格尺寸', 'iline-v-fixed-connector', '固定式连接头'),
            {
              id: 'iline-v-feed-unit-etb',
              label: '馈电单元（ETB）',
              children: [
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 馈电单元（ETB）',
                  'iline-v-etb-cable-terminal',
                  '电缆馈电箱-终端式'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 馈电单元（ETB）',
                  'iline-v-etb-middle-feed-unit',
                  '中间馈电单元'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 馈电单元（ETB）',
                  'iline-v-etb-terminal-end',
                  '终端封'
                )
              ]
            },
            {
              id: 'iline-v-feed-unit-fe',
              label: '馈电单元（FE）',
              children: [
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 馈电单元（FE）',
                  'iline-v-fe-standard-flange',
                  '标准法兰'
                )
              ]
            },
            {
              id: 'iline-v-quick-flange-qf',
              label: '快接法兰（QF）',
              children: [
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 快接法兰（QF）',
                  'iline-v-qf-quick-flange',
                  '与配电柜连接的快接法兰'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 快接法兰（QF）',
                  'iline-v-qf-expansion-joint',
                  '膨胀节'
                )
              ]
            },
            {
              id: 'iline-v-turning-part',
              label: '转向部件',
              children: [
                createPendingSectionNode('I-LINE-V / 规格尺寸 / 转向部件', 'iline-v-turning-t', 'T接'),
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 转向部件',
                  'iline-v-horizontal-elbow',
                  '水平弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 转向部件',
                  'iline-v-vertical-elbow',
                  '立式弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 转向部件',
                  'iline-v-combined-elbow',
                  '组合弯头'
                )
              ]
            },
            {
              id: 'iline-v-special-part',
              label: '特殊部件',
              children: [
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 特殊部件',
                  'iline-v-taper-joint',
                  '变容节'
                )
              ]
            },
            {
              id: 'iline-v-accessories',
              label: '附件',
              children: [
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 附件',
                  'iline-v-wall-flange',
                  '穿墙法兰'
                )
              ]
            },
            {
              id: 'iline-v-install-hanger',
              label: '安装吊架',
              children: [
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 安装吊架',
                  'iline-v-flat-hanger',
                  '平面吊架'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 安装吊架',
                  'iline-v-vertical-hanger',
                  '立式吊架'
                )
              ]
            },
            {
              id: 'iline-v-vertical-bracket',
              label: '垂直安装用支架',
              children: [
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 垂直安装用支架',
                  'iline-v-vertical-fixed-bracket',
                  '垂直固定式支架'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 垂直安装用支架',
                  'iline-v-vertical-spring-bracket',
                  '垂直弹簧式支架'
                )
              ]
            },
            {
              id: 'iline-v-breaker-box-size',
              label: '配施耐德电气断路器插接箱',
              children: [
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-v-plug-in-box-16-250',
                  '插入式插接箱（16A-250A）'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-v-plug-in-box-16-100',
                  '插入式插接箱（16A-100A）'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-v-fixed-box-400-500',
                  '固定式插接箱（400A-500A）'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-v-fixed-box-630-1000',
                  '固定式插接箱（630A-1000A）'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-v-double-outlet-box-25x2',
                  '一出二插接箱（25A*2）'
                ),
                createPendingSectionNode(
                  'I-LINE-V / 规格尺寸 / 配施耐德电气断路器插接箱',
                  'iline-v-double-outlet-box-250x2',
                  '一出二插接箱（250A*2）'
                )
              ]
            }
          ]
        }
      ]
    },
    {
      id: 'iline-track',
      label: 'I-LINE-Track',
      children: [
        createPendingSectionNode('I-LINE-Track', 'iline-track-product-image', '产品概览图'),
        createPendingSectionNode('I-LINE-Track', 'iline-track-parameter-overview', '参数概览'),
        {
          id: 'iline-track-model-rules',
          label: '型号编制规则',
          layout: 'compact',
          children: [
            createPendingSectionNode('I-LINE-Track / 型号编制规则', 'iline-track-busbar', '母线'),
            createPendingSectionNode('I-LINE-Track / 型号编制规则', 'iline-track-tap-off-box', '插接箱'),
            createPendingSectionNode('I-LINE-Track / 型号编制规则', 'iline-track-switch-feed-box', '开关馈电箱')
          ]
        },
        {
          id: 'iline-track-product-model',
          label: '产品型号',
          layout: 'compact',
          children: [
            createPendingSectionNode('I-LINE-Track / 产品型号', 'iline-track-flange', '法兰'),
            {
              id: 'iline-track-feed-unit',
              label: '馈电单元',
              children: [
                createPendingSectionNode(
                  'I-LINE-Track / 产品型号 / 馈电单元',
                  'iline-track-cable-feed-box',
                  '电缆馈电箱'
                ),
                createPendingSectionNode(
                  'I-LINE-Track / 产品型号 / 馈电单元',
                  'iline-track-switch-feed-unit',
                  '开关馈电箱'
                )
              ]
            },
            createPendingSectionNode('I-LINE-Track / 产品型号', 'iline-track-elbow', '弯头'),
            createPendingSectionNode('I-LINE-Track / 产品型号', 'iline-track-joint', '接头'),
            createPendingSectionNode('I-LINE-Track / 产品型号', 'iline-track-mounting-bracket', '安装支架'),
            createPendingSectionNode('I-LINE-Track / 产品型号', 'iline-track-end-cap', '端封')
          ]
        },
        {
          id: 'iline-track-size',
          label: '规格尺寸',
          layout: 'grid',
          children: [
            createPendingSectionNode('I-LINE-Track / 规格尺寸', 'iline-track-straight-section', '直身段'),
            createPendingSectionNode('I-LINE-Track / 规格尺寸', 'iline-track-joint-with-cover', '接头（带盖板）'),
            createPendingSectionNode('I-LINE-Track / 规格尺寸', 'iline-track-joint-without-cover', '接头（不带盖板）'),
            createPendingSectionNode('I-LINE-Track / 规格尺寸', 'iline-track-standard-flange', '标准法兰'),
            {
              id: 'iline-track-turning-part',
              label: '转向部件',
              children: [
                createPendingSectionNode(
                  'I-LINE-Track / 规格尺寸 / 转向部件',
                  'iline-track-horizontal-elbow',
                  '水平弯头'
                ),
                createPendingSectionNode(
                  'I-LINE-Track / 规格尺寸 / 转向部件',
                  'iline-track-t-elbow',
                  'T型弯头'
                )
              ]
            },
            createPendingSectionNode('I-LINE-Track / 规格尺寸', 'iline-track-double-rod-hanger', '双杆吊架'),
            createPendingSectionNode('I-LINE-Track / 规格尺寸', 'iline-track-single-rod-hanger', '单杆吊架'),
            {
              id: 'iline-track-box',
              label: '插接箱',
              children: [
                createPendingSectionNode(
                  'I-LINE-Track / 规格尺寸 / 插接箱',
                  'iline-track-mobile-industrial-socket-63',
                  '63A移动工业插座'
                ),
                createPendingSectionNode(
                  'I-LINE-Track / 规格尺寸 / 插接箱',
                  'iline-track-fixed-industrial-socket-63',
                  '63A固定工业插座'
                ),
                createPendingSectionNode(
                  'I-LINE-Track / 规格尺寸 / 插接箱',
                  'iline-track-mobile-industrial-socket-128',
                  '128A移动工业插座'
                )
              ]
            }
          ]
        }
      ]
    },
    {
      id: 'fireproof-busway',
      label: '耐火母线',
      children: [
        createPendingSectionNode('耐火母线', 'fireproof-overview', '产品概览'),
        createPendingSectionNode('耐火母线', 'fireproof-parameter-overview', '参数概览'),
        {
          id: 'fireproof-product-model',
          label: '产品型号',
          layout: 'grid',
          children: [
            createPendingSectionNode('耐火母线 / 产品型号', 'fireproof-straight-section-model', '直身段'),
            createPendingSectionNode('耐火母线 / 产品型号', 'fireproof-joint-model', '连接头'),
            createPendingSectionNode('耐火母线 / 产品型号', 'fireproof-flange-model', '法兰'),
            createPendingSectionNode('耐火母线 / 产品型号', 'fireproof-elbow-model', '弯头'),
            createPendingSectionNode('耐火母线 / 产品型号', 'fireproof-t-joint-model', 'T接'),
            createPendingSectionNode('耐火母线 / 产品型号', 'fireproof-expansion-joint-model', '膨胀节'),
            createPendingSectionNode('耐火母线 / 产品型号', 'fireproof-terminal-end-model', '终端封'),
            createPendingSectionNode('耐火母线 / 产品型号', 'fireproof-flat-hanger-model', '平面吊架'),
            createPendingSectionNode('耐火母线 / 产品型号', 'fireproof-vertical-hanger-model', '立式吊架'),
            createPendingSectionNode('耐火母线 / 产品型号', 'fireproof-fixed-hanger-model', '固定吊架'),
            createPendingSectionNode('耐火母线 / 产品型号', 'fireproof-spring-hanger-model', '弹簧吊架'),
            createPendingSectionNode('耐火母线 / 产品型号', 'fireproof-vertical-lifting-tool-model', '竖直吊装工具')
          ]
        },
        {
          id: 'fireproof-size',
          label: '规格尺寸',
          layout: 'grid',
          children: [
            createPendingSectionNode('耐火母线 / 规格尺寸', 'fireproof-straight-section-size', '直身段'),
            {
              id: 'fireproof-feed-unit-fe',
              label: '馈电单元（FE）',
              children: [
                createPendingSectionNode(
                  '耐火母线 / 规格尺寸 / 馈电单元（FE）',
                  'fireproof-fe-standard-flange',
                  '标准法兰'
                )
              ]
            },
            {
              id: 'fireproof-turning-part',
              label: '转向部件',
              children: [
                createPendingSectionNode(
                  '耐火母线 / 规格尺寸 / 转向部件',
                  'fireproof-vertical-elbow',
                  '立式弯头'
                ),
                createPendingSectionNode(
                  '耐火母线 / 规格尺寸 / 转向部件',
                  'fireproof-horizontal-elbow',
                  '水平弯头'
                ),
                createPendingSectionNode(
                  '耐火母线 / 规格尺寸 / 转向部件',
                  'fireproof-t-joint-size',
                  'T接'
                ),
                createPendingSectionNode(
                  '耐火母线 / 规格尺寸 / 转向部件',
                  'fireproof-combined-elbow',
                  '组合弯头'
                )
              ]
            },
            createPendingSectionNode('耐火母线 / 规格尺寸', 'fireproof-terminal-end-size', '终端封'),
            createPendingSectionNode('耐火母线 / 规格尺寸', 'fireproof-expansion-joint-size', '膨胀节'),
            {
              id: 'fireproof-install-hanger',
              label: '安装吊架',
              children: [
                createPendingSectionNode(
                  '耐火母线 / 规格尺寸 / 安装吊架',
                  'fireproof-flat-hanger-size',
                  '平面吊架'
                )
              ]
            },
            {
              id: 'fireproof-vertical-bracket',
              label: '垂直安装用支架',
              children: [
                createPendingSectionNode(
                  '耐火母线 / 规格尺寸 / 垂直安装用支架',
                  'fireproof-vertical-fixed-bracket',
                  '垂直固定式支架'
                ),
                createPendingSectionNode(
                  '耐火母线 / 规格尺寸 / 垂直安装用支架',
                  'fireproof-vertical-spring-bracket',
                  '垂直弹簧式支架'
                )
              ]
            }
          ]
        }
      ]
    }
  ]
};

const DEFAULT_PRODUCT_GUIDE_TREE = normalizeGuideTreeContent(PRODUCT_GUIDE_TREE);

Page({
  data: {
    assistantAvatar: '../../图标/Gemini_Generated_Image_aicku5aicku5aick.png',
    userInfo: null,
    inputValue: '',
    voiceSupported: true,
    isVoiceRecording: false,
    voiceStatusText: '',
    loading: false,
    isGenerating: false,
    editorVisible: false,
    editorTargetId: '',
    editorText: '',
    showDeepThinkingIndicator: false,
    lastMsgId: 'msg_0',
    scrollTop: 0,
    scrollIntoView: '',
    guideHeaderTitle: DEFAULT_PRODUCT_GUIDE_TREE.title,
    guideHeaderHint: DEFAULT_PRODUCT_GUIDE_TREE.hint,
    guideBreadcrumbs: [],
    guideOptions: [],
    guideOptionsCompact: false,
    guidePanelTitle: '',
    guidePanelHint: '',
    guideOptionTitle: '',
    guidePathIndices: [],
    selectedGuideLeafId: '',
    feedbackKeyboardHeight: 0,
    feedbackModalHeight: 0,
    feedbackModalOffset: 0,
    feedbackModalStyle: DEFAULT_FEEDBACK_MODAL_STYLE,
    feedbackVisible: false,
    feedbackTargetId: '',
    feedbackSelectedType: '',
    feedbackDetail: '',
    feedbackSubmitting: false,
    feedbackOptions: [
      '没有帮助',
      '知识过时',
      '问题理解错误',
      '事实错误',
      '回答不准确',
      '内容有害/不健康',
      '前后回复不一致'
    ],
    messages: [
      {
        id: 'msg_0',
        type: 'ai',
        text: '您好！我是施耐德母线小助手，可以协助您查询施耐德产品的选型、参数概览、型号信息、规格尺寸、适用场景及常见问题，也可以点击上方快捷导航，快速查看您想了解的内容；您也可以咨询部分友商产品的相关信息或直接向我提问，例如：请介绍某个型号、介绍施耐德工厂、I-Line Track有哪些特点或优势？等等。我会为您整理并解答。',
        showAssistantActions: false,
        displayNodes: [
          {
            type: 'text',
            lines: [
              {
                segments: [
                  { text: '您好！我是施耐德母线小助手，可以协助您查询施耐德产品的选型、参数概览、型号信息、规格尺寸、适用场景及常见问题，也可以点击上方快捷导航，快速查看您想了解的内容；您也可以咨询部分友商产品的相关信息或直接向我提问，例如：请介绍某个型号、介绍施耐德工厂、I-Line Track有哪些特点或优势？等等。我会为您整理并解答。', bold: false, code: false }
                ]
              }
            ]
          }
        ]
      }
    ]
  },

  async onLoad() {
    if (!app.requireLogin()) return;
    this.activeSocketTask = null;
    this.windowHeight = this.resolveWindowHeight();
    this.recordRecognitionManager = null;
    this.voiceInputBase = '';
    this.voiceStatusTimer = null;
    this.voiceStopByUser = false;
    this.stopRequested = false;
    this.activePromptText = '';
    this.activePromptDisplayText = '';
    this.activePromptStartedAt = 0;
    this.currentResponseStartMeta = null;
    this.currentResponseMessageId = '';
    this.deepThinkingTimer = null;
    this.deepThinkingMsgId = '';
    this.scrollBottomTimer = null;
    this.isRestoringConversationCache = false;
    this.isClearingConversationCache = false;
    this.initialMessages = this.cloneMessages(this.data.messages || []);
    this.guideTree = DEFAULT_PRODUCT_GUIDE_TREE;
    this.guideTreeLoaded = false;
    this.initVoiceRecognition();
    await this.syncUserInfo();
    await this.initGuide();
    this.restoreConversationCache();
  },

  onHide() {
    this.persistConversationCache();
  },

  onUnload() {
    this.persistConversationCache();
    this.clearDeepThinkingTimer();
    this.deepThinkingMsgId = '';
    this.clearScrollBottomTimer();
    this.clearVoiceStatusTimer();
    this.stopVoiceRecognition();
  },

  async onShow() {
    if (!app.requireLogin()) return;
    await this.syncUserInfo();
    if (!this.data.guideBreadcrumbs.length) {
      await this.initGuide();
    }
  },

  async syncUserInfo() {
    if (!app.globalData.userInfo) {
      app.getUserProfile();
    }

    this.setData({
      userInfo: await app.resolveAvatarFields(
        app.globalData.userInfo || wx.getStorageSync('userInfo') || null,
        { avatarField: 'avatar_url', fileIdField: 'avatar_file_id' }
      )
    });
  },

  resolveWindowHeight() {
    if (typeof wx.getWindowInfo === 'function') {
      try {
        const windowInfo = wx.getWindowInfo();
        const windowHeight = Number(windowInfo && windowInfo.windowHeight);
        if (Number.isFinite(windowHeight) && windowHeight > 0) {
          return windowHeight;
        }
      } catch (err) {
        // ignore
      }
    }

    try {
      const windowInfo = wx.getWindowInfo();
      const windowHeight = Number(windowInfo && windowInfo.windowHeight);
      return Number.isFinite(windowHeight) && windowHeight > 0 ? windowHeight : 0;
    } catch (err) {
      return 0;
    }
  },

  buildFeedbackModalStyle(offset = 0) {
    const safeOffset = Math.max(0, Number(offset) || 0);
    return `transform: translateY(-${safeOffset}px);`;
  },

  syncFeedbackModalHeight(callback) {
    if (!this.data.feedbackVisible) {
      if (typeof callback === 'function') {
        callback(0);
      }
      return;
    }

    wx.createSelectorQuery()
      .in(this)
      .select('.feedback-modal')
      .boundingClientRect((rect) => {
        const modalHeight = Math.ceil(Number(rect && rect.height) || 0);
        this.setData({
          feedbackModalHeight: modalHeight
        }, () => {
          if (typeof callback === 'function') {
            callback(modalHeight);
          }
        });
      })
      .exec();
  },

  updateFeedbackModalPosition(keyboardHeight = 0, modalHeight = this.data.feedbackModalHeight) {
    const resolvedWindowHeight = this.windowHeight || this.resolveWindowHeight();
    this.windowHeight = resolvedWindowHeight;

    const safeKeyboardHeight = Math.max(0, Number(keyboardHeight) || 0);
    const safeModalHeight = Math.max(0, Number(modalHeight) || 0);
    const nextOffset = calculateFeedbackModalOffset({
      windowHeight: resolvedWindowHeight,
      modalHeight: safeModalHeight,
      keyboardHeight: safeKeyboardHeight,
      safeGap: FEEDBACK_MODAL_SAFE_GAP
    });

    this.setData({
      feedbackKeyboardHeight: safeKeyboardHeight,
      feedbackModalOffset: nextOffset,
      feedbackModalStyle: this.buildFeedbackModalStyle(nextOffset)
    });
  },

  onInput(e) {
    this.setData({
      inputValue: e.detail.value
    }, () => {
      this.persistConversationCache();
    });
  },

  initVoiceRecognition() {
    if (!wechatSIPlugin || typeof wechatSIPlugin.getRecordRecognitionManager !== 'function') {
      this.setData({
        voiceSupported: false,
        voiceStatusText: '当前环境暂不支持语音识别'
      });
      return;
    }

    const manager = wechatSIPlugin.getRecordRecognitionManager();
    if (!manager) {
      this.setData({
        voiceSupported: false,
        voiceStatusText: '当前环境暂不支持语音识别'
      });
      return;
    }

    this.recordRecognitionManager = manager;
    this.bindVoiceRecognitionEvents(manager);
    this.setData({
      voiceSupported: true,
      voiceStatusText: ''
    });
  },

  bindVoiceRecognitionEvents(manager) {
    if (!manager || this.voiceRecognitionBound) {
      return;
    }

    this.voiceRecognitionBound = true;

    manager.onStart = () => {
      this.setData({
        isVoiceRecording: true
      });
      this.setVoiceStatus('正在聆听，点击麦克风结束', false);
    };

    manager.onRecognize = (res = {}) => {
      const mergedInput = this.mergeVoiceInput(this.voiceInputBase, res.result);
      if (mergedInput) {
        this.setData({
          inputValue: mergedInput
        }, () => {
          this.persistConversationCache();
        });
      }
    };

    manager.onStop = (res = {}) => {
      const mergedInput = this.mergeVoiceInput(this.voiceInputBase, res.result);

      this.setData({
        isVoiceRecording: false,
        inputValue: mergedInput || this.voiceInputBase || this.data.inputValue || ''
      }, () => {
        this.persistConversationCache();
      });

      if (mergedInput && mergedInput.trim()) {
        this.setVoiceStatus('语音已转换为文字', true);
      } else {
        this.setVoiceStatus('未识别到清晰语音，请重试', true);
      }
    };

    manager.onError = (err = {}) => {
      console.warn('Voice recognition error:', err);
      this.setData({
        isVoiceRecording: false
      });
      this.setVoiceStatus(this.getVoiceErrorMessage(err), true);
    };
  },

  mergeVoiceInput(baseText, voiceText) {
    const base = String(baseText || '').trim();
    const voice = String(voiceText || '').trim();
    if (!base) {
      return voice;
    }
    if (!voice) {
      return base;
    }
    return /[\s，。！？；：,.!?;:]$/.test(base) ? `${base}${voice}` : `${base} ${voice}`;
  },

  clearVoiceStatusTimer() {
    if (this.voiceStatusTimer) {
      clearTimeout(this.voiceStatusTimer);
      this.voiceStatusTimer = null;
    }
  },

  setVoiceStatus(text = '', autoClear = false) {
    this.clearVoiceStatusTimer();
    this.setData({
      voiceStatusText: text
    });

    if (autoClear && text) {
      this.voiceStatusTimer = setTimeout(() => {
        this.voiceStatusTimer = null;
        this.setData({
          voiceStatusText: '',
          isVoiceRecording: false
        });
      }, 2200);
    }
  },

  getSettingAsync() {
    return new Promise((resolve, reject) => {
      wx.getSetting({
        success: resolve,
        fail: reject
      });
    });
  },

  authorizeScopeAsync(scope) {
    return new Promise((resolve, reject) => {
      wx.authorize({
        scope,
        success: resolve,
        fail: reject
      });
    });
  },

  openSettingAsync() {
    return new Promise((resolve, reject) => {
      wx.openSetting({
        success: resolve,
        fail: reject
      });
    });
  },

  showVoicePermissionModal() {
    return new Promise((resolve) => {
      wx.showModal({
        title: '需要麦克风权限',
        content: '开启麦克风权限后，才可以使用语音识别输入。',
        confirmText: '去开启',
        success: async (res) => {
          if (!res.confirm) {
            resolve(false);
            return;
          }

          try {
            const settingRes = await this.openSettingAsync();
            resolve(!!(settingRes.authSetting && settingRes.authSetting['scope.record']));
          } catch (err) {
            resolve(false);
          }
        },
        fail: () => resolve(false)
      });
    });
  },

  async ensureRecordPermission() {
    try {
      const settingRes = await this.getSettingAsync();
      const authSetting = (settingRes && settingRes.authSetting) || {};

      if (authSetting['scope.record'] === true) {
        return true;
      }

      if (authSetting['scope.record'] === false) {
        return this.showVoicePermissionModal();
      }

      await this.authorizeScopeAsync('scope.record');
      return true;
    } catch (err) {
      return this.showVoicePermissionModal();
    }
  },

  getVoiceErrorMessage(err = {}) {
    const rawMessage = String(err.msg || err.errMsg || err.message || '').trim();
    const normalized = rawMessage.toLowerCase();

    if (normalized.includes('auth deny') || normalized.includes('authorize') || normalized.includes('permission')) {
      return '未开启麦克风权限';
    }

    if (normalized.includes('cancel')) {
      return '已取消语音识别';
    }

    return '语音识别失败，请重试';
  },

  async onVoiceTap() {
    if (!app.requireLogin()) return;

    if (this.data.loading || this.data.isGenerating) {
      wx.showToast({
        title: '请等待当前回答结束',
        icon: 'none'
      });
      return;
    }

    if (!this.data.voiceSupported || !this.recordRecognitionManager) {
      wx.showToast({
        title: '当前环境暂不支持语音识别',
        icon: 'none'
      });
      return;
    }

    if (this.data.isVoiceRecording) {
      this.stopVoiceRecognition(true);
      return;
    }

    const granted = await this.ensureRecordPermission();
    if (!granted) {
      this.setVoiceStatus('未开启麦克风权限', true);
      return;
    }

    this.startVoiceRecognition();
  },

  startVoiceRecognition() {
    if (!this.recordRecognitionManager || this.data.isVoiceRecording) {
      return;
    }

    this.voiceInputBase = String(this.data.inputValue || '').trim();
    this.voiceStopByUser = false;
    this.setVoiceStatus('正在准备录音...', false);

    try {
      this.recordRecognitionManager.start({
        duration: VOICE_RECOGNITION_MAX_DURATION,
        lang: 'zh_CN'
      });
    } catch (err) {
      console.warn('Voice recognition start failed:', err);
      this.setData({
        isVoiceRecording: false
      });
      this.setVoiceStatus('语音识别启动失败，请重试', true);
    }
  },

  stopVoiceRecognition(triggeredByUser = false) {
    this.voiceStopByUser = triggeredByUser;

    if (!this.recordRecognitionManager) {
      this.setData({
        isVoiceRecording: false
      });
      return;
    }

    try {
      this.recordRecognitionManager.stop();
      if (triggeredByUser) {
        this.setVoiceStatus('正在转换语音...', false);
      }
    } catch (err) {
      console.warn('Voice recognition stop failed:', err);
      this.setData({
        isVoiceRecording: false
      });
    }
  },

  cloneMessages(messages = []) {
    return JSON.parse(JSON.stringify(messages || []));
  },

  getConversationCacheUserId() {
    const userId =
      app.globalData.userId ||
      (typeof wx !== 'undefined' && typeof wx.getStorageSync === 'function'
        ? wx.getStorageSync('userId')
        : '') ||
      '';
    return String(userId || '').trim() || 'guest';
  },

  getConversationCacheKey() {
    return buildChatSessionStorageKey(this.getConversationCacheUserId());
  },

  collectConversationCacheState() {
    const messages = this.cloneMessages(this.data.messages || []);
    const lastMessage = messages.length ? messages[messages.length - 1] : null;

    return {
      messages,
      inputValue: String(this.data.inputValue || ''),
      guidePathIndices: Array.isArray(this.data.guidePathIndices) ? this.data.guidePathIndices.slice() : [],
      selectedGuideLeafId: String(this.data.selectedGuideLeafId || ''),
      lastMsgId: String(this.data.lastMsgId || (lastMessage && lastMessage.id) || 'msg_0')
    };
  },

  persistConversationCache() {
    if (
      this.isRestoringConversationCache ||
      this.isClearingConversationCache ||
      typeof wx === 'undefined' ||
      typeof wx.setStorageSync !== 'function'
    ) {
      return;
    }

    try {
      wx.setStorageSync(
        this.getConversationCacheKey(),
        serializeChatSessionState(this.collectConversationCacheState())
      );
    } catch (err) {
      console.warn('persistConversationCache failed:', err);
    }
  },

  clearConversationCache() {
    if (typeof wx === 'undefined' || typeof wx.removeStorageSync !== 'function') {
      return;
    }

    try {
      wx.removeStorageSync(this.getConversationCacheKey());
    } catch (err) {
      console.warn('clearConversationCache failed:', err);
    }
  },

  restoreConversationCache() {
    if (typeof wx === 'undefined' || typeof wx.getStorageSync !== 'function') {
      return false;
    }

    let restoredState = null;
    try {
      restoredState = deserializeChatSessionState(wx.getStorageSync(this.getConversationCacheKey()));
    } catch (err) {
      restoredState = null;
    }

    if (!restoredState) {
      return false;
    }

    const restoredMessages = (restoredState.messages || []).length
      ? restoredState.messages.map((message) => this.decorateMessage(message))
      : this.cloneMessages(this.initialMessages || []).map((message) => this.decorateMessage(message));
    const lastMessage = restoredMessages.length ? restoredMessages[restoredMessages.length - 1] : null;
    const lastMsgId = String(restoredState.lastMsgId || (lastMessage && lastMessage.id) || 'msg_0');

    this.isRestoringConversationCache = true;
    this.applyGuidePath(restoredState.guidePathIndices || []);
    this.setData({
      messages: restoredMessages,
      inputValue: String(restoredState.inputValue || ''),
      loading: false,
      isGenerating: false,
      editorVisible: false,
      editorTargetId: '',
      editorText: '',
      showDeepThinkingIndicator: false,
      lastMsgId,
      scrollTop: 0,
      scrollIntoView: ''
    }, () => {
      this.isRestoringConversationCache = false;
      this.scrollToBottom(this.getNextScrollTop());
      this.persistConversationCache();
    });
    return true;
  },

  closeActiveSocket(reason = 'client-finished') {
    const socketTask = this.activeSocketTask;
    this.activeSocketTask = null;
    if (socketTask && typeof socketTask.close === 'function') {
      try {
        socketTask.close({ code: 1000, reason });
      } catch (err) {
        // ignore close errors
      }
    }
  },

  resetConversation() {
    this.clearDeepThinkingTimer();
    this.deepThinkingMsgId = '';
    this.clearVoiceStatusTimer();
    this.stopRequested = true;
    this.activePromptText = '';
    this.activePromptDisplayText = '';
    this.stopVoiceRecognition();
    this.closeActiveSocket('clear-screen');

    const initialMessages = this.cloneMessages(this.initialMessages || this.data.messages || []);
    const lastMsgId = initialMessages.length
      ? initialMessages[initialMessages.length - 1].id
      : 'msg_0';

    this.setData({
      messages: initialMessages,
      inputValue: '',
      isVoiceRecording: false,
      voiceStatusText: '',
      loading: false,
      isGenerating: false,
      editorVisible: false,
      editorTargetId: '',
      editorText: '',
      showDeepThinkingIndicator: false,
      lastMsgId,
      scrollTop: 0,
      scrollIntoView: ''
    });
  },

  /**
   * 文件功能菜单入口
   * 点击"+"按钮弹出功能选择菜单，支持扩展后续文件处理功能
   */
  onOpenFileMenu() {
    wx.showActionSheet({
      itemList: ['招标文件资料提取', '招标文件智能分析'],
      itemColor: '#1E293B',
      success: (res) => {
        if (res.tapIndex === 0) {
          // 模式一：招标文件资料提取
          wx.navigateTo({
            url: '/pages/bidding-result/bidding-result?mode=extract',
          });
        } else if (res.tapIndex === 1) {
          // 模式二：招标文件智能分析
          wx.navigateTo({
            url: '/pages/bidding-result/bidding-result?mode=analyze',
          });
        }
      },
    });
  },

  onClearScreen() {
    const initialCount = (this.initialMessages || []).length;
    const hasMessages = (this.data.messages || []).length > initialCount;
    const hasDraft = !!String(this.data.inputValue || '').trim();
    const hasEditorText = !!String(this.data.editorText || '').trim();
    const hasPendingState =
      this.data.loading ||
      this.data.isGenerating ||
      this.data.editorVisible ||
      this.data.showDeepThinkingIndicator;

    if (!hasMessages && !hasDraft && !hasEditorText && !hasPendingState) {
      wx.showToast({
        title: '当前没有可清空内容',
        icon: 'none'
      });
      return;
    }

    this.isClearingConversationCache = true;
    this.resetConversation();
    this.clearConversationCache();
    this.isClearingConversationCache = false;
    wx.showToast({
      title: '已清屏',
      icon: 'success'
    });
  },

  clearDeepThinkingTimer() {
    if (this.deepThinkingTimer) {
      clearTimeout(this.deepThinkingTimer);
      this.deepThinkingTimer = null;
    }
  },

  scheduleDeepThinkingIndicator() {
    this.clearDeepThinkingTimer();
    this.deepThinkingTimer = setTimeout(() => {
      this.deepThinkingTimer = null;

      if ((!this.data.loading && !this.data.isGenerating) || this.deepThinkingMsgId) {
        return;
      }

      const indicatorMsg = this.createMessage('ai', DEEP_THINKING_TEXT, {
        sourceType: 'status',
        showAssistantActions: false,
        statusIndicator: true
      });
      this.deepThinkingMsgId = indicatorMsg.id;

      this.setData({
        messages: [...this.data.messages, indicatorMsg],
        showDeepThinkingIndicator: true,
        lastMsgId: indicatorMsg.id,
        scrollTop: this.nextScrollTop()
      }, () => {
        this.persistConversationCache();
      });
    }, DEEP_THINKING_DELAY);
  },

  stripDeepThinkingIndicator(messages = []) {
    this.clearDeepThinkingTimer();

    if (!this.deepThinkingMsgId) {
      return messages;
    }

    const nextMessages = messages.filter((message) => message.id !== this.deepThinkingMsgId);
    this.deepThinkingMsgId = '';
    return nextMessages;
  },

  initGuide() {
    return this.loadGuideTree().then(() => {
      this.applyGuidePath([]);
    });
  },

  async loadGuideTree(force = false) {
    if (!force && this.guideTreeLoaded) {
      return this.getActiveGuideTree();
    }

    const fallbackTree = DEFAULT_PRODUCT_GUIDE_TREE;

    try {
      const remoteTree = await app.request({
        url: '/api/product-guides/tree',
        timeout: 25000,
        retryCount: 1,
        debugTag: 'guideTree'
      });

      if (remoteTree && remoteTree.id === 'root' && Array.isArray(remoteTree.children)) {
        const normalizedRemoteTree = normalizeGuideTreeContent(remoteTree);
        this.guideTree = normalizedRemoteTree;
        this.guideTreeLoaded = true;
        this.setData({
          guideHeaderTitle: normalizedRemoteTree.title || fallbackTree.title,
          guideHeaderHint: normalizedRemoteTree.hint || fallbackTree.hint
        });
        return normalizedRemoteTree;
      }
    } catch (err) {
      console.warn('loadGuideTree fallback to local tree:', err);
    }

    this.guideTree = fallbackTree;
    this.guideTreeLoaded = true;
    this.setData({
      guideHeaderTitle: fallbackTree.title,
      guideHeaderHint: fallbackTree.hint
    });
    return fallbackTree;
  },

  getActiveGuideTree() {
    return this.guideTree || DEFAULT_PRODUCT_GUIDE_TREE;
  },

  onGuideOptionTap(e) {
    if (this.data.loading || this.data.isGenerating) return;

    const optionIndex = Number(e.currentTarget.dataset.index);
    const basePath = this.isGuideLeafPath(this.data.guidePathIndices)
      ? this.data.guidePathIndices.slice(0, -1)
      : this.data.guidePathIndices.slice();
    const nextPath = [...basePath, optionIndex];
    const nextNode = this.getGuideNodeByPath(nextPath);

    this.applyGuidePath(nextPath);

    if (this.isGuideLeafNode(nextNode)) {
      this.appendGuideAnswer(nextPath, nextNode);
    }
  },

  onGuideBreadcrumbTap(e) {
    if (this.data.loading || this.data.isGenerating) return;

    const depth = Number(e.currentTarget.dataset.depth);
    const nextPath = this.data.guidePathIndices.slice(0, depth);
    this.applyGuidePath(nextPath);
  },

  appendGuideAnswer(pathIndices, node) {
    const selectionText = this.buildGuideBreadcrumbs(pathIndices)
      .slice(1)
      .map((item) => item.label)
      .join(' / ');

    const userMsg = this.createMessage('user', selectionText);
    const aiMsg = this.createMessage('ai', node.answer || '该节点暂未配置答案。', {
      sourceType: 'guide'
    });

    this.setData({
      messages: [...this.data.messages, userMsg, aiMsg],
      lastMsgId: aiMsg.id,
      scrollTop: this.nextScrollTop()
    }, () => {
      this.persistConversationCache();
    });
  },

  applyGuidePath(pathIndices) {
    const guideTree = this.getActiveGuideTree();
    const currentNode = this.getGuideNodeByPath(pathIndices);
    const isLeaf = this.isGuideLeafNode(currentNode);
    const optionOwnerNode = isLeaf ? this.getGuideNodeByPath(pathIndices.slice(0, -1)) : currentNode;
    const optionChildren = ((optionOwnerNode && optionOwnerNode.children) || []).filter(Boolean);
    const guideOptionsCompact =
      optionOwnerNode && optionOwnerNode.layout === 'compact'
        ? true
        : optionOwnerNode && optionOwnerNode.layout === 'grid'
          ? false
          : optionChildren.length > 8 || optionChildren.some((child) => (child.label || '').length > 14);

    this.setData({
      guidePathIndices: pathIndices,
      guideBreadcrumbs: this.buildGuideBreadcrumbs(pathIndices),
      guideOptions: optionChildren.map((child, index) => ({
        id: child.id,
        label: child.label,
        index
      })),
      guideOptionsCompact,
      guidePanelTitle: '',
      guidePanelHint: '',
      guideOptionTitle:
        optionOwnerNode && optionOwnerNode.id === guideTree.id
          ? '请选择具体产品'
          : `请选择 ${(optionOwnerNode && optionOwnerNode.label) || '当前分类'} 下的问题`,
      selectedGuideLeafId: isLeaf && currentNode ? currentNode.id : ''
    }, () => {
      this.persistConversationCache();
    });
  },

  buildGuideBreadcrumbs(pathIndices) {
    const guideTree = this.getActiveGuideTree();
    const breadcrumbs = [
      {
        id: guideTree.id,
        label: guideTree.label,
        depth: 0
      }
    ];

    let currentNode = guideTree;
    pathIndices.forEach((childIndex, pathIndex) => {
      currentNode = (currentNode.children || [])[childIndex];
      if (!currentNode) {
        return;
      }

      breadcrumbs.push({
        id: currentNode.id,
        label: currentNode.label,
        depth: pathIndex + 1
      });
    });

    return breadcrumbs.map((item, index) => ({
      ...item,
      isLast: index === breadcrumbs.length - 1
    }));
  },

  getGuideNodeByPath(pathIndices) {
    let currentNode = this.getActiveGuideTree();

    pathIndices.forEach((childIndex) => {
      currentNode = (currentNode.children || [])[childIndex] || currentNode;
    });

    return currentNode;
  },

  isGuideLeafPath(pathIndices) {
    return this.isGuideLeafNode(this.getGuideNodeByPath(pathIndices));
  },

  isGuideLeafNode(node) {
    return !node || !node.children || node.children.length === 0;
  },

  async onSend() {
    if (!app.requireLogin()) return;
    if (this.data.isVoiceRecording) {
      wx.showToast({
        title: '请先结束语音识别',
        icon: 'none'
      });
      return;
    }

    const text = (this.data.inputValue || '').trim();
    if (!text) return;

    await this.submitPrompt(text);
  },

  async submitPrompt(promptText, options = {}) {
    if (!app.requireLogin()) return;

    const finalPrompt = String(promptText || '').trim();
    const userText = String(options.userText || finalPrompt).trim();
    if (!finalPrompt || !userText || this.data.loading || this.data.isGenerating) return;

    const userMsg = this.createMessage('user', userText, {
      showUserActions: true,
      sourceType: 'chat'
    });
    this.stopRequested = false;
    this.activePromptText = finalPrompt;
    this.activePromptDisplayText = userText;
    this.activePromptStartedAt = Date.now();
    this.currentResponseStartMeta = null;
    this.currentResponseMessageId = '';
    this.setData({
      messages: [...this.data.messages, userMsg],
      inputValue: '',
      loading: true,
      isGenerating: true,
      showDeepThinkingIndicator: false,
      editorVisible: false,
      editorTargetId: '',
      editorText: '',
      feedbackVisible: false,
      feedbackTargetId: '',
      feedbackSelectedType: '',
      feedbackDetail: '',
      lastMsgId: userMsg.id,
      scrollTop: this.nextScrollTop()
    }, () => {
      this.persistConversationCache();
    });
    this.scheduleDeepThinkingIndicator();

    try {
      await this.streamChatViaSocket(finalPrompt);
    } catch (err) {
      if (this.stopRequested) {
        console.info('[ai-chat] generation stopped by user');
        return;
      }
      console.error('WebSocket stream chat error:', err);
      console.info('[ai-chat] websocket stream failed, switching to blocking fallback chat');
      await this.fallbackChat(finalPrompt, userText);
    } finally {
      this.activePromptText = '';
      this.activePromptDisplayText = '';
      this.activePromptStartedAt = 0;
      this.currentResponseStartMeta = null;
      this.currentResponseMessageId = '';
      this.stopRequested = false;
    }
  },

  onCopyMessage(e) {
    const messageId = e.currentTarget.dataset.id;
    const message = this.getMessageById(messageId);
    if (!message || !message.text) return;

    wx.setClipboardData({
      data: message.text,
      success: () => {
        wx.showToast({
          title: '已复制',
          icon: 'none'
        });
      }
    });
  },

  onEditUserMessage(e) {
    if (this.data.loading || this.data.isGenerating) return;

    const messageId = e.currentTarget.dataset.id;
    const message = this.getMessageById(messageId);
    if (!message || message.type !== 'user' || !message.text) return;

    this.openInlineEditor(messageId, message.text);
  },

  onRegenerateMessage(e) {
    if (this.data.loading || this.data.isGenerating) return;

    const messageId = e.currentTarget.dataset.id;
    const message = this.getMessageById(messageId);
    if (!message || message.type !== 'ai') return;

    const promptText = String(message.promptText || '').trim();
    const promptDisplayText = String(message.promptDisplayText || promptText).trim();
    if (!promptText) return;

    this.setData({
      editorVisible: false,
      editorTargetId: '',
      editorText: ''
    });
    this.submitPrompt(promptText, {
      userText: promptDisplayText || promptText
    });
  },

  async onOpenFeedback(e) {
    if (this.data.loading || this.data.isGenerating) return;
    if (this.data.feedbackSubmitting) return;

    const messageId = e.currentTarget.dataset.id;
    const message = this.getMessageById(messageId);
    if (!message || message.type !== 'ai') return;

    const feedbackMessageId = this.getAssistantMessageId(message);
    if (!feedbackMessageId) {
      wx.showToast({
        title: '当前回答缺少消息ID，暂不能提交反馈',
        icon: 'none'
      });
      return;
    }

    this.setData({
      feedbackSubmitting: true,
      feedbackVisible: false,
      feedbackTargetId: messageId,
      feedbackSelectedType: '没有帮助',
      feedbackDetail: ''
    });

    try {
      await app.request({
        url: '/api/chat/feedback',
        method: 'POST',
        data: {
          message_id: feedbackMessageId,
          like_type: 'dislike',
          feedback_info: {
            ProblemCategories: ['没有帮助'],
            ProblemDetail: '一键反馈：用户点击反馈按钮，认为该回答需要人工复核',
            question: String(message.promptDisplayText || message.promptText || '').trim(),
            answer: String(message.text || '').trim(),
            local_message_id: String(message.id || '').trim(),
            hiagent_message_id: String(message.messageId || message.message_id || message.MessageID || '').trim()
          }
        },
        timeout: 30000,
        retryCount: 0,
        dedupe: false,
        debugTag: 'ai-feedback'
      });

      wx.showToast({
        title: '反馈已提交',
        icon: 'none'
      });

      this.setData({
        feedbackTargetId: '',
        feedbackSelectedType: '',
        feedbackDetail: '',
        feedbackSubmitting: false
      });
    } catch (err) {
      console.error('Submit feedback error:', err);
      this.setData({
        feedbackTargetId: '',
        feedbackSelectedType: '',
        feedbackDetail: '',
        feedbackSubmitting: false
      });
      wx.showToast({
        title: '反馈提交失败，请稍后再试',
        icon: 'none'
      });
    }
  },

  onCloseFeedback() {
    if (this.data.feedbackSubmitting) return;

    this.setData({
      feedbackKeyboardHeight: 0,
      feedbackModalHeight: 0,
      feedbackModalOffset: 0,
      feedbackModalStyle: DEFAULT_FEEDBACK_MODAL_STYLE,
      feedbackVisible: false,
      feedbackTargetId: '',
      feedbackSelectedType: '',
      feedbackDetail: ''
    });
  },

  onSelectFeedbackType(e) {
    const feedbackType = String(e.currentTarget.dataset.type || '').trim();
    if (!feedbackType) return;

    this.setData({
      feedbackSelectedType: feedbackType
    });
  },

  onFeedbackDetailInput(e) {
    this.setData({
      feedbackDetail: e.detail.value || ''
    });
  },

  onFeedbackFocus(e) {
    const keyboardHeight = Number(e.detail && e.detail.height) || 0;
    this.syncFeedbackModalHeight((modalHeight) => {
      this.updateFeedbackModalPosition(keyboardHeight, modalHeight);
    });
  },

  onFeedbackBlur() {
    this.updateFeedbackModalPosition(0, this.data.feedbackModalHeight);
  },

  async onSubmitFeedback() {
    if (this.data.feedbackSubmitting) return;

    const targetId = this.data.feedbackTargetId;
    const message = this.getMessageById(targetId);
    const feedbackType = String(this.data.feedbackSelectedType || '').trim();
    if (!message || !feedbackType) return;

    const feedbackMessageId = this.getAssistantMessageId(message);
    if (!feedbackMessageId) {
      wx.showToast({
        title: '当前回答缺少消息ID，暂不能提交反馈',
        icon: 'none'
      });
      return;
    }

    this.setData({ feedbackSubmitting: true });

    try {
      await app.request({
        url: '/api/chat/feedback',
        method: 'POST',
        data: {
          message_id: feedbackMessageId,
          like_type: 'dislike',
          feedback_info: {
            ProblemCategories: [feedbackType],
            ProblemDetail: String(this.data.feedbackDetail || '').trim(),
            question: String(message.promptDisplayText || message.promptText || '').trim(),
            answer: String(message.text || '').trim(),
            local_message_id: String(message.id || '').trim(),
            hiagent_message_id: String(message.messageId || message.message_id || message.MessageID || '').trim()
          }
        },
        timeout: 30000,
        retryCount: 0,
        dedupe: false,
        debugTag: 'ai-feedback'
      });

      wx.showToast({
        title: '反馈已提交',
        icon: 'none'
      });

      this.setData({
        feedbackKeyboardHeight: 0,
        feedbackModalHeight: 0,
        feedbackModalOffset: 0,
        feedbackModalStyle: DEFAULT_FEEDBACK_MODAL_STYLE,
        feedbackVisible: false,
        feedbackTargetId: '',
        feedbackSelectedType: '',
        feedbackDetail: '',
        feedbackSubmitting: false
      });
    } catch (err) {
      console.error('Submit feedback error:', err);
      this.setData({ feedbackSubmitting: false });
      wx.showToast({
        title: '反馈提交失败，请稍后再试',
        icon: 'none'
      });
    }
  },

  noop() {},

  openInlineEditor(targetId, text) {
    this.setData({
      editorVisible: true,
      editorTargetId: targetId,
      editorText: text,
      scrollTop: this.nextScrollTop()
    });
  },

  onInlineEditorInput(e) {
    this.setData({
      editorText: e.detail.value
    });
  },

  cancelInlineEdit() {
    this.setData({
      editorVisible: false,
      editorTargetId: '',
      editorText: ''
    });
  },

  async submitInlineEdit() {
    const editorText = String(this.data.editorText || '').trim();
    if (!editorText || this.data.loading || this.data.isGenerating) return;

    this.setData({
      editorVisible: false,
      editorTargetId: '',
      editorText: ''
    });
    await this.submitPrompt(editorText);
  },

  stopGeneration() {
    if (!this.data.isGenerating) return;

    this.stopRequested = true;
    const messages = this.data.messages || [];
    const lastMsg = messages[messages.length - 1];
    const partialText =
      lastMsg && lastMsg.type === 'ai' && lastMsg.streaming
        ? String(lastMsg.text || '')
        : '';

    if (partialText) {
      this.finishStreamingMessage(partialText, {
        promptText: this.activePromptText,
        promptDisplayText: this.activePromptDisplayText,
        showAssistantActions: true,
        sourceType: 'chat'
      });
    } else {
      const messages = this.stripDeepThinkingIndicator([...(this.data.messages || [])]);
      this.setData({
        messages,
        loading: false,
        isGenerating: false,
        showDeepThinkingIndicator: false,
        lastMsgId: messages.length ? messages[messages.length - 1].id : 'msg_0',
        scrollTop: this.nextScrollTop()
      }, () => {
        this.persistConversationCache();
      });
    }

    this.closeActiveSocket('user-stopped');
  },

  getMessageById(messageId) {
    return (this.data.messages || []).find((message) => message.id === messageId) || null;
  },

  getAssistantMessageId(message) {
    return String(
      (message && (message.messageId || message.message_id || message.MessageID)) ||
      ''
    ).trim();
  },

  async fallbackChat(text, userText = text) {
    try {
      const res = await app.request({
        url: '/api/chat',
        method: 'POST',
        data: {
          message: text,
          user_id: app.globalData.userId || 'guest'
        },
        timeout: 60000,
        retryCount: 0,
        debugTag: 'ai-fallback-chat'
      });

      const replyText =
        (res && res.reply) ||
        (typeof res === 'string' ? res : '') ||
        '抱歉，我现在暂时无法回答。';
      const messageId = String((res && (res.message_id || res.MessageID || res.messageId)) || '').trim();

      console.info('[ai-chat] fallback chat produced final reply');
      const responseStartMeta = this.currentResponseStartMeta || this.getResponseStartMeta();
      this.finishStreamingMessage(replyText, {
        promptText: text,
        promptDisplayText: userText,
        showAssistantActions: true,
        sourceType: 'chat',
        ...(messageId ? { messageId } : {}),
        ...responseStartMeta
      });
    } catch (err) {
      console.error('Fallback chat error:', err);
      this.finishStreamingMessage('网络有点不稳定，请稍后再试。', {
        showAssistantActions: false
      });
    }
  },

  async streamChatViaSocket(message) {
    const containerConfig = app.getCallContainerConfig();
    const runtimeConfig = app.getRuntimeConfig();
    if (
      !containerConfig ||
      !runtimeConfig.serviceName ||
      !wx.cloud ||
      typeof wx.cloud.connectContainer !== 'function'
    ) {
      throw new Error('Missing websocket container config');
    }

    const connection = await wx.cloud.connectContainer({
      config: containerConfig,
      service: runtimeConfig.serviceName,
      path: '/api/chat/ws'
    });
    const socketTask = connection && connection.socketTask;
    if (
      !socketTask ||
      typeof socketTask.onMessage !== 'function' ||
      typeof socketTask.send !== 'function'
    ) {
      throw new Error('connectContainer did not return a usable socketTask');
    }
    this.activeSocketTask = socketTask;

    return new Promise((resolve, reject) => {
      let fullText = '';
      let hasReceivedChunk = false;
      let settled = false;
      let idleTimer = null;
      let opened = false;

      const closeSocketSilently = () => {
        if (!socketTask || typeof socketTask.close !== 'function') {
          return;
        }

        try {
          socketTask.close({ code: 1000, reason: 'client-finished' });
        } catch (err) {
          // ignore close errors
        }
      };

      const clearTimers = () => {
        if (idleTimer) {
          clearTimeout(idleTimer);
          idleTimer = null;
        }
      };

      const refreshIdleTimer = () => {
        clearTimers();
        idleTimer = setTimeout(() => {
          closeSocketSilently();
          finishError(new Error('WebSocket stream idle timeout'));
        }, 65000);
      };

      const finishSuccess = () => {
        if (settled) return;
        settled = true;
        clearTimers();
        this.activeSocketTask = null;
        this.setData({ isGenerating: false });
        resolve(fullText);
      };

      const finishError = (err) => {
        if (settled) return;
        settled = true;
        clearTimers();
        this.activeSocketTask = null;
        this.setData({ isGenerating: false });
        reject(err instanceof Error ? err : new Error('WebSocket stream error'));
      };

      const sendPayload = () => {
        if (opened) {
          return;
        }

        if (this.stopRequested) {
          closeSocketSilently();
          finishSuccess();
          return;
        }

        opened = true;
        refreshIdleTimer();
        console.info('[ai-chat] websocket stream opened via connectContainer');
        socketTask.send({
          data: JSON.stringify({
            token: app.globalData.token || '',
            user_id: app.globalData.userId || 'guest',
            message
          }),
          fail: (err) => finishError(err)
        });
      };

      if (typeof socketTask.onOpen === 'function') {
        socketTask.onOpen(sendPayload);
      } else {
        sendPayload();
      }

      socketTask.onMessage((res) => {
        if (this.stopRequested) {
          return;
        }

        refreshIdleTimer();

        const payloadText =
          typeof res.data === 'string'
            ? res.data
            : '';
        if (!payloadText) {
          return;
        }

        let payload = null;
        try {
          payload = JSON.parse(payloadText);
        } catch (err) {
          return;
        }

        if (!payload || typeof payload !== 'object') {
          return;
        }

        if (payload.type === 'ping') {
          return;
        }

        if (payload.type === 'meta') {
          const messageId = String(payload.message_id || payload.MessageID || payload.messageId || '').trim();
          if (messageId) {
            this.currentResponseMessageId = messageId;
            this.attachMessageIdToStreamingMessage(messageId);
          }
          return;
        }

        if (payload.type === 'chunk') {
          const chunk = payload.chunk || '';
          if (!chunk) return;

          let responseStartMeta = {};
          if (!hasReceivedChunk) {
            hasReceivedChunk = true;
            this.currentResponseStartMeta = this.getResponseStartMeta();
            responseStartMeta = this.currentResponseStartMeta;
            console.info('[ai-chat] first websocket chunk received via connectContainer');
          }

          fullText += chunk;
          this.upsertStreamingMessage(fullText, responseStartMeta);
          return;
        }

        if (payload.type === 'done') {
          console.info('[ai-chat] websocket stream completed', {
            chunkLength: fullText.length
          });
          /*
          this.finishStreamingMessage(fullText || '鎶辨瓑锛屾垜鐜板湪鏆傛椂鏃犳硶鍥炵瓟銆?);
          closeSocketSilently();
          finishSuccess();
          return;
        }

          */
          this.finishStreamingMessage(fullText || '抱歉，我现在暂时无法回答。', {
            promptText: message,
            promptDisplayText: this.activePromptDisplayText || message,
            showAssistantActions: true,
            sourceType: 'chat',
            ...(this.currentResponseMessageId ? { messageId: this.currentResponseMessageId } : {})
          });
          closeSocketSilently();
          finishSuccess();
          return;
        }

        if (payload.type === 'error') {
          closeSocketSilently();
          finishError(new Error(payload.message || 'WebSocket chat error'));
        }
      });

      if (typeof socketTask.onError === 'function') {
        socketTask.onError((err) => {
          if (this.stopRequested) {
            finishSuccess();
            return;
          }
          console.warn('[ai-chat] websocket connection error', err);
          finishError(err);
        });
      }

      if (typeof socketTask.onClose === 'function') {
        socketTask.onClose((res) => {
          if (settled) return;

          if (this.stopRequested) {
            console.info('[ai-chat] websocket stream stopped by user', res);
            finishSuccess();
            return;
          }

          if (hasReceivedChunk && fullText) {
            console.info('[ai-chat] websocket closed after streamed response', res);
            /*
            this.finishStreamingMessage(fullText || '鎶辨瓑锛屾垜鐜板湪鏆傛椂鏃犳硶鍥炵瓟銆?);
            finishSuccess();
            return;
          }

            */
            this.finishStreamingMessage(fullText || '抱歉，我现在暂时无法回答。', {
              promptText: message,
              promptDisplayText: this.activePromptDisplayText || message,
              showAssistantActions: true,
              sourceType: 'chat',
              ...(this.currentResponseMessageId ? { messageId: this.currentResponseMessageId } : {})
            });
            finishSuccess();
            return;
          }

          console.warn('[ai-chat] websocket closed before streamed response', res);
          finishError(new Error('WebSocket closed before any response'));
        });
      }
    });
  },

  streamChat(message) {
    return new Promise((resolve, reject) => {
      const header = {
        'Content-Type': 'application/json'
      };

      if (app.globalData.token) {
        header.Authorization = `Bearer ${app.globalData.token}`;
      }

      let fullText = '';
      let buffer = '';
      let chunkedWorking = false;
      let hasLoggedFirstChunk = false;

      const requestOptions = {
        path: '/api/chat/stream',
        method: 'POST',
        data: {
          user_id: app.globalData.userId || 'guest',
          message
        },
        header: app.buildServiceHeaders(header),
        timeout: 60000,
        enableChunked: true,
        responseType: 'text',
        success: (res) => {
          if (chunkedWorking) {
            console.info('[ai-chat] stream succeeded via callContainer chunk stream', {
              chunkLength: fullText.length
            });
            this.finishStreamingMessage(fullText || '抱歉，我现在暂时无法回答。');
            resolve(fullText);
            return;
          }

          const rawText = typeof res.data === 'string' ? res.data : '';
          const parsedText = this.parseSseResponse(rawText);
          if (parsedText) {
            console.info('[ai-chat] stream succeeded via callContainer success payload parse', {
              parsedLength: parsedText.length
            });
            this.finishStreamingMessage(parsedText, this.currentResponseStartMeta || this.getResponseStartMeta());
            resolve(parsedText);
            return;
          }

          console.warn('[ai-chat] stream success callback had no recognizable SSE payload');
          reject(new Error('No stream data received'));
        },
        fail: (err) => {
          console.warn('[ai-chat] stream callContainer failed', err);
          reject(err);
        }
      };

      const containerConfig = app.getCallContainerConfig();
      if (containerConfig) {
        requestOptions.config = containerConfig;
      }

      const requestTask = wx.cloud.callContainer(requestOptions);

      if (requestTask && typeof requestTask.onChunkReceived === 'function') {
        requestTask.onChunkReceived((response) => {
          chunkedWorking = true;

          let text = '';
          try {
            text = this.decodeUtf8(new Uint8Array(response.data));
          } catch (err) {
            return;
          }

          buffer += text;
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          lines.forEach((line) => {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data:')) return;

            const jsonStr = trimmed.slice(5).trim();
            if (!jsonStr) return;

            try {
              const data = JSON.parse(jsonStr);
              const chunk = data.chunk || '';
              if (!chunk || chunk === '[DONE]') return;

              let responseStartMeta = {};
              if (!hasLoggedFirstChunk) {
                hasLoggedFirstChunk = true;
                this.currentResponseStartMeta = this.getResponseStartMeta();
                responseStartMeta = this.currentResponseStartMeta;
                console.info('[ai-chat] first stream chunk received via callContainer');
              }

              fullText += chunk;
              this.upsertStreamingMessage(fullText, responseStartMeta);
            } catch (err) {
              // ignore invalid partial chunk
            }
          });
        });
      }
    });
  },

  /*
  streamChat(message) {
    return new Promise((resolve, reject) => {
      const containerConfig = app.getCallContainerConfig();
      const runtimeConfig = app.getRuntimeConfig();
      if (
        !containerConfig ||
        !runtimeConfig.serviceName ||
        !wx.cloud ||
        typeof wx.cloud.connectContainer !== 'function'
      ) {
        reject(new Error('Missing websocket container config'));
        return;
      }

      let fullText = '';
      let hasReceivedChunk = false;
      let settled = false;

      const finishSuccess = () => {
        if (settled) return;
        settled = true;
        // legacy fallback branch kept disabled
        this.finishStreamingMessage(fullText || '鎶辨瓑锛屾垜鐜板湪鏆傛椂鏃犳硶鍥炵瓟銆?);
        resolve(fullText);
        // legacy fallback branch kept disabled
        this.finishStreamingMessage(fullText || '抱歉，我现在暂时无法回答。');
        resolve(fullText);
      };

      const finishError = (err) => {
        if (settled) return;
        settled = true;
        reject(err);
      };

      const socketTask = wx.cloud.connectContainer({
        config: containerConfig,
        service: runtimeConfig.serviceName,
        path: '/api/chat/ws'
      });

      socketTask.onOpen(() => {
        console.info('[ai-chat] websocket stream opened');
        socketTask.send({
          data: JSON.stringify({
            token: app.globalData.token || '',
            user_id: app.globalData.userId || 'guest',
            message
          })
        });
      });

      socketTask.onMessage((res) => {
        let payloadText = '';
        if (typeof res.data === 'string') {
          payloadText = res.data;
        } else if (res.data) {
          try {
            payloadText = this.decodeUtf8(new Uint8Array(res.data));
          } catch (err) {
            payloadText = '';
          }
        }

        if (!payloadText) {
          return;
        }

        let payload = null;
        try {
          payload = JSON.parse(payloadText);
        } catch (err) {
          return;
        }

        if (!payload || typeof payload !== 'object') {
          return;
        }

        if (payload.type === 'chunk') {
          const chunk = payload.chunk || '';
          if (!chunk) return;

          let responseStartMeta = {};
          if (!hasReceivedChunk) {
            hasReceivedChunk = true;
            this.currentResponseStartMeta = this.getResponseStartMeta();
            responseStartMeta = this.currentResponseStartMeta;
            console.info('[ai-chat] first websocket chunk received via cloud container');
          }

          fullText += chunk;
          this.upsertStreamingMessage(fullText, responseStartMeta);
          return;
        }

        if (payload.type === 'done') {
          console.info('[ai-chat] websocket stream completed', {
            chunkLength: fullText.length
          });
          try {
            socketTask.close({ code: 1000, reason: 'done' });
          } catch (err) {
            // ignore close errors
          }

          if (!hasReceivedChunk) {
            finishError(new Error('No stream data received'));
            return;
          }

          finishSuccess();
          return;
        }

        if (payload.type === 'error') {
          console.warn('[ai-chat] websocket stream failed', payload);
          try {
            socketTask.close({ code: 1011, reason: 'error' });
          } catch (err) {
            // ignore close errors
          }
          finishError(new Error(payload.message || 'WebSocket chat error'));
        }
      });

      socketTask.onError((err) => {
        console.warn('[ai-chat] websocket connection error', err);
        finishError(err instanceof Error ? err : new Error('WebSocket connection error'));
      });

      socketTask.onClose((res) => {
        if (settled) return;

        if (hasReceivedChunk && fullText) {
          console.info('[ai-chat] websocket closed after streaming response', res);
          finishSuccess();
          return;
        }

        console.warn('[ai-chat] websocket closed before any chunk', res);
        finishError(new Error('No stream data received'));
      });
    });
  },
  */

  streamChat(message) {
    return new Promise((resolve, reject) => {
      const containerConfig = app.getCallContainerConfig();
      const runtimeConfig = app.getRuntimeConfig();
      if (
        !containerConfig ||
        !runtimeConfig.serviceName ||
        !wx.cloud ||
        typeof wx.cloud.connectContainer !== 'function'
      ) {
        reject(new Error('Missing websocket container config'));
        return;
      }

      let fullText = '';
      let hasReceivedChunk = false;
      let settled = false;

      const finishSuccess = () => {
        if (settled) return;
        settled = true;
        this.finishStreamingMessage(fullText || '抱歉，我现在暂时无法回答。');
        resolve(fullText);
      };

      const finishError = (err) => {
        if (settled) return;
        settled = true;
        reject(err);
      };

      const socketTask = wx.cloud.connectContainer({
        config: containerConfig,
        service: runtimeConfig.serviceName,
        path: '/api/chat/ws'
      });

      socketTask.onOpen(() => {
        console.info('[ai-chat] websocket stream opened');
        socketTask.send({
          data: JSON.stringify({
            token: app.globalData.token || '',
            user_id: app.globalData.userId || 'guest',
            message
          })
        });
      });

      socketTask.onMessage((res) => {
        let payloadText = '';
        if (typeof res.data === 'string') {
          payloadText = res.data;
        } else if (res.data) {
          try {
            payloadText = this.decodeUtf8(new Uint8Array(res.data));
          } catch (err) {
            payloadText = '';
          }
        }

        if (!payloadText) {
          return;
        }

        let payload = null;
        try {
          payload = JSON.parse(payloadText);
        } catch (err) {
          return;
        }

        if (!payload || typeof payload !== 'object') {
          return;
        }

        if (payload.type === 'chunk') {
          const chunk = payload.chunk || '';
          if (!chunk) return;

          let responseStartMeta = {};
          if (!hasReceivedChunk) {
            hasReceivedChunk = true;
            this.currentResponseStartMeta = this.getResponseStartMeta();
            responseStartMeta = this.currentResponseStartMeta;
            console.info('[ai-chat] first websocket chunk received via cloud container');
          }

          fullText += chunk;
          this.upsertStreamingMessage(fullText, responseStartMeta);
          return;
        }

        if (payload.type === 'done') {
          console.info('[ai-chat] websocket stream completed', {
            chunkLength: fullText.length
          });
          try {
            socketTask.close({ code: 1000, reason: 'done' });
          } catch (err) {
            // ignore close errors
          }

          if (!hasReceivedChunk) {
            finishError(new Error('No stream data received'));
            return;
          }

          finishSuccess();
          return;
        }

        if (payload.type === 'error') {
          console.warn('[ai-chat] websocket stream failed', payload);
          try {
            socketTask.close({ code: 1011, reason: 'error' });
          } catch (err) {
            // ignore close errors
          }
          finishError(new Error(payload.message || 'WebSocket chat error'));
        }
      });

      socketTask.onError((err) => {
        console.warn('[ai-chat] websocket connection error', err);
        finishError(err instanceof Error ? err : new Error('WebSocket connection error'));
      });

      socketTask.onClose((res) => {
        if (settled) return;

        if (hasReceivedChunk && fullText) {
          console.info('[ai-chat] websocket closed after streaming response', res);
          finishSuccess();
          return;
        }

        console.warn('[ai-chat] websocket closed before any chunk', res);
        finishError(new Error('No stream data received'));
      });
    });
  },

  createMessage(type, text, extra = {}) {
    return this.decorateMessage({
      id: `msg_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
      type,
      text,
      ...extra
    });
  },

  decorateMessage(message) {
    const normalizedMessage = {
      ...message,
      text: String((message && message.text) || '')
    };
    const streaming = !!normalizedMessage.streaming;
    let displayNodes = this.parseRichContent(normalizedMessage.text, { streaming });
    displayNodes = this.stripGuideLeadInNodes(displayNodes, normalizedMessage);
    const hasImageContent = displayNodes.some((node) => node.type === 'image' || node.type === 'image_loading');
    const thinkingStatus =
      normalizedMessage.type === 'ai' &&
      this.isThinkingStatusMessage(normalizedMessage.text);

    return {
      ...normalizedMessage,
      displayNodes,
      hasImageContent,
      thinkingStatus,
      showAssistantActions: thinkingStatus ? false : normalizedMessage.showAssistantActions
    };
  },

  stripGuideLeadInNodes(displayNodes, message) {
    if (
      !Array.isArray(displayNodes) ||
      !displayNodes.length ||
      !message ||
      message.sourceType !== 'guide'
    ) {
      return displayNodes;
    }

    const firstImageIndex = displayNodes.findIndex((node) => node.type === 'image');
    if (firstImageIndex <= 0) {
      return displayNodes;
    }

    const leadInNodes = displayNodes.slice(0, firstImageIndex);
    const canStripLeadIn = leadInNodes.every((node) =>
      ['text', 'heading', 'list'].includes(node.type)
    );

    return canStripLeadIn ? displayNodes.slice(firstImageIndex) : displayNodes;
  },

  isThinkingStatusMessage(text) {
    const normalized = String(text || '')
      .replace(/\s+/g, '')
      .replace(/[^\u4e00-\u9fa5a-zA-Z0-9]/g, '');

    if (!normalized) {
      return false;
    }

    return (
      /^(正在|当前)?(进行)?(深度)?思考(中)?(请稍候|请稍等|稍候|稍等|请等待|等待)?$/.test(normalized) ||
      /^(正在进行)?深度思考/.test(normalized) ||
      /^(正在)?思考中/.test(normalized)
    );
  },

  formatResponseStartDuration(durationMs) {
    const safeDuration = Number(durationMs);
    if (!Number.isFinite(safeDuration) || safeDuration < 0) {
      return '';
    }

    const seconds = safeDuration / 1000;
    const displaySeconds =
      seconds < 10
        ? seconds.toFixed(1)
        : String(Math.round(seconds));

    return `用时 ${displaySeconds} 秒`;
  },

  getResponseStartMeta(startedAt = this.activePromptStartedAt) {
    const safeStartedAt = Number(startedAt);
    if (!Number.isFinite(safeStartedAt) || safeStartedAt <= 0) {
      return {};
    }

    const responseStartMs = Math.max(0, Date.now() - safeStartedAt);
    const responseStartText = this.formatResponseStartDuration(responseStartMs);
    return responseStartText
      ? {
          responseStartMs,
          responseStartText
        }
      : {};
  },

  attachMessageIdToStreamingMessage(messageId) {
    const cleanMessageId = String(messageId || '').trim();
    if (!cleanMessageId) return;

    const messages = [...(this.data.messages || [])];
    const lastMsg = messages[messages.length - 1];
    if (!lastMsg || lastMsg.type !== 'ai' || !lastMsg.streaming) {
      return;
    }

    messages[messages.length - 1] = this.decorateMessage({
      ...lastMsg,
      messageId: cleanMessageId
    });

    this.setData({ messages }, () => {
      this.persistConversationCache();
    });
  },

  upsertStreamingMessage(text, responseStartMeta = {}) {
    const safeText = normalizeAgentReplyText(text);
    const messages = this.stripDeepThinkingIndicator([...(this.data.messages || [])]);
    const lastMsg = messages[messages.length - 1];

    if (lastMsg && lastMsg.type === 'ai' && lastMsg.streaming) {
      messages[messages.length - 1] = this.decorateMessage({
        ...lastMsg,
        ...responseStartMeta,
        text: safeText,
        promptText: lastMsg.promptText || this.activePromptText,
        promptDisplayText: lastMsg.promptDisplayText || this.activePromptDisplayText,
        ...(this.currentResponseMessageId ? { messageId: this.currentResponseMessageId } : {}),
        showAssistantActions: false
      });

      this.setData({
        messages,
        loading: false,
        isGenerating: true,
        showDeepThinkingIndicator: false,
        lastMsgId: lastMsg.id,
        scrollTop: this.nextScrollTop()
      }, () => {
        this.persistConversationCache();
      });
      return;
    }

    const streamMsg = this.createMessage('ai', safeText, {
      streaming: true,
      promptText: this.activePromptText,
      promptDisplayText: this.activePromptDisplayText,
      ...(this.currentResponseMessageId ? { messageId: this.currentResponseMessageId } : {}),
      showAssistantActions: false,
      sourceType: 'chat',
      ...responseStartMeta
    });
    messages.push(streamMsg);

    this.setData({
      messages,
      loading: false,
      isGenerating: true,
      showDeepThinkingIndicator: false,
      lastMsgId: streamMsg.id,
      scrollTop: this.nextScrollTop()
    }, () => {
      this.persistConversationCache();
    });
  },

  finishStreamingMessage(text, extra = {}) {
    const safeText = normalizeAgentReplyText(text);
    const messages = this.stripDeepThinkingIndicator([...(this.data.messages || [])]);
    const lastMsg = messages[messages.length - 1];
    const promptText =
      extra.promptText !== undefined
        ? extra.promptText
        : lastMsg && lastMsg.type === 'ai'
          ? lastMsg.promptText
          : '';
    const promptDisplayText =
      extra.promptDisplayText !== undefined
        ? extra.promptDisplayText
        : lastMsg && lastMsg.type === 'ai'
          ? lastMsg.promptDisplayText
          : '';
    const showAssistantActions =
      extra.showAssistantActions !== undefined
        ? extra.showAssistantActions
        : !!promptText;
    const resolvedMessageId =
      extra.messageId !== undefined
        ? extra.messageId
        : lastMsg && lastMsg.type === 'ai'
          ? lastMsg.messageId
          : this.currentResponseMessageId;

    if (lastMsg && lastMsg.type === 'ai' && lastMsg.streaming) {
      messages[messages.length - 1] = this.decorateMessage({
        ...lastMsg,
        ...extra,
        text: safeText,
        streaming: false,
        promptText,
        promptDisplayText,
        ...(resolvedMessageId ? { messageId: resolvedMessageId } : {}),
        showAssistantActions
      });

      this.setData({
        messages,
        loading: false,
        isGenerating: false,
        showDeepThinkingIndicator: false,
        lastMsgId: lastMsg.id,
        scrollTop: this.nextScrollTop()
      }, () => {
        this.persistConversationCache();
      });
      return;
    }

    const aiMsg = this.createMessage('ai', safeText, {
      ...extra,
      promptText,
      promptDisplayText,
      ...(resolvedMessageId ? { messageId: resolvedMessageId } : {}),
      showAssistantActions
    });
    messages.push(aiMsg);

    this.setData({
      messages,
      loading: false,
      isGenerating: false,
      showDeepThinkingIndicator: false,
      lastMsgId: aiMsg.id,
      scrollTop: this.nextScrollTop()
    }, () => {
      this.persistConversationCache();
    });
  },

  clearScrollBottomTimer() {
    if (this.scrollBottomTimer) {
      clearTimeout(this.scrollBottomTimer);
      this.scrollBottomTimer = null;
    }
  },

  getNextScrollTop() {
    return (Number(this.data.scrollTop) || 0) + 100000;
  },

  scrollToBottom(scrollTop = this.getNextScrollTop()) {
    const nextTop = Number(scrollTop) || 0;
    this.clearScrollBottomTimer();

    this.scrollBottomTimer = setTimeout(() => {
      const applyScroll = (contentHeight = 0) => {
        const targetTop = Math.max(nextTop, Math.ceil(contentHeight) + 100000);
        this.setData({
          scrollTop: targetTop,
          scrollIntoView: ''
        }, () => {
          const runFinalScroll = () => {
            this.setData({
              scrollTop: targetTop + 100000,
              scrollIntoView: 'chatBottomAnchor'
            });
          };

          if (typeof wx.nextTick === 'function') {
            wx.nextTick(runFinalScroll);
          } else {
            setTimeout(runFinalScroll, 16);
          }
        });
      };

      wx.createSelectorQuery()
        .in(this)
        .select('.chat-list')
        .boundingClientRect((rect) => {
          applyScroll(rect && rect.height ? rect.height : 0);
        })
        .exec();
    }, 20);
  },

  nextScrollTop() {
    const nextTop = this.getNextScrollTop();
    this.scrollToBottom(nextTop);
    return nextTop;
  },

  parseSseResponse(responseText) {
    if (!responseText) return '';

    let result = '';
    responseText.split('\n').forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed.startsWith('data:')) return;

      const jsonStr = trimmed.slice(5).trim();
      if (!jsonStr) return;

      try {
        const data = JSON.parse(jsonStr);
        const chunk = data.chunk || '';
        if (chunk && chunk !== '[DONE]') {
          result += chunk;
        }
      } catch (err) {
        // ignore
      }
    });

    return result;
  },

  decodeUtf8(uint8Array) {
    let result = '';
    let i = 0;

    while (i < uint8Array.length) {
      const c = uint8Array[i];
      if (c < 128) {
        result += String.fromCharCode(c);
        i += 1;
      } else if (c > 191 && c < 224) {
        result += String.fromCharCode(((c & 31) << 6) | (uint8Array[i + 1] & 63));
        i += 2;
      } else if (c > 223 && c < 240) {
        result += String.fromCharCode(
          ((c & 15) << 12) |
          ((uint8Array[i + 1] & 63) << 6) |
          (uint8Array[i + 2] & 63)
        );
        i += 3;
      } else {
        const codePoint =
          ((c & 7) << 18) |
          ((uint8Array[i + 1] & 63) << 12) |
          ((uint8Array[i + 2] & 63) << 6) |
          (uint8Array[i + 3] & 63);
        const offset = codePoint - 0x10000;
        result += String.fromCharCode(0xd800 + (offset >> 10), 0xdc00 + (offset & 0x3ff));
        i += 4;
      }
    }

    return result;
  },

  parseRichContent(text, options = {}) {
    if (!text) {
      return [];
    }

    const streaming = !!options.streaming;
    const lines = text.replace(/\r/g, '').split('\n');
    const nodes = [];
    let textBuffer = [];
    let i = 0;

    const flushText = () => {
      if (!textBuffer.length) return;
      const content = textBuffer.join('\n');
      const parsedNodes = this.parseTextBlock(content, options);
      if (parsedNodes.length) {
        nodes.push(...parsedNodes);
      }
      textBuffer = [];
    };

    while (i < lines.length) {
      const line = lines[i];
      const trimmed = (line || '').trim();

      if (/^```/.test(trimmed)) {
        flushText();
        const codeLines = [];
        i += 1;
        while (i < lines.length && !/^```/.test((lines[i] || '').trim())) {
          codeLines.push(lines[i]);
          i += 1;
        }
        if (i < lines.length) i += 1;
        nodes.push({
          type: 'code',
          code: codeLines.join('\n')
        });
        continue;
      }

      const headingMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
      if (headingMatch) {
        flushText();
        nodes.push({
          type: 'heading',
          level: headingMatch[1].length,
          segments: this.parseInlineStyles(headingMatch[2].trim())
        });
        i += 1;
        continue;
      }

      if (/^(\-|\*|\+)\s+/.test(trimmed)) {
        flushText();
        const items = [];
        while (i < lines.length && /^(\-|\*|\+)\s+/.test((lines[i] || '').trim())) {
          const itemText = (lines[i] || '').trim().replace(/^(\-|\*|\+)\s+/, '');
          if (this.hasRenderableImage(itemText)) {
            if (items.length) {
              nodes.push({
                type: 'list',
                ordered: false,
                items
              });
              items.length = 0;
            }
            nodes.push(...this.parseTextBlock(itemText, options));
            i += 1;
            continue;
          }

          items.push({
            segments: this.parseInlineStyles(itemText)
          });
          i += 1;
        }
        if (items.length) {
          nodes.push({
            type: 'list',
            ordered: false,
            items
          });
        }
        continue;
      }

      if (/^\d+\.\s+/.test(trimmed)) {
        flushText();
        const items = [];
        while (i < lines.length && /^\d+\.\s+/.test((lines[i] || '').trim())) {
          const itemText = (lines[i] || '').trim().replace(/^\d+\.\s+/, '');
          if (this.hasRenderableImage(itemText)) {
            if (items.length) {
              nodes.push({
                type: 'list',
                ordered: true,
                items
              });
              items.length = 0;
            }
            nodes.push(...this.parseTextBlock(itemText, options));
            i += 1;
            continue;
          }

          items.push({
            segments: this.parseInlineStyles(itemText)
          });
          i += 1;
        }
        if (items.length) {
          nodes.push({
            type: 'list',
            ordered: true,
            items
          });
        }
        continue;
      }

      if (this.isMarkdownTableRow(trimmed) || (streaming && this.isPotentialMarkdownTableRow(trimmed))) {
        const tableLines = [];
        while (
          i < lines.length &&
          (this.isMarkdownTableRow((lines[i] || '').trim()) ||
            (streaming && this.isPotentialMarkdownTableRow((lines[i] || '').trim())))
        ) {
          tableLines.push((lines[i] || '').trim());
          i += 1;
        }

        const tableNode = this.parseMarkdownTable(tableLines);
        if (tableNode) {
          flushText();
          nodes.push(tableNode);
          continue;
        }

        if (streaming && this.shouldShowTableLoading(tableLines)) {
          flushText();
          nodes.push(this.createLoadingNode('table'));
          continue;
        }

        textBuffer.push(...tableLines);
        continue;
      }

      if (this.isMarkdownImage(trimmed)) {
        flushText();
        nodes.push(...this.parseTextBlock(trimmed, options));
        i += 1;
        continue;
      }

      textBuffer.push(line);
      i += 1;
    }

    flushText();
    return nodes;
  },

  parseTextBlock(content, options = {}) {
    const source = content || '';
    if (!source.trim()) return [];

    const streaming = !!options.streaming;
    const nodes = [];
    let textLines = [];
    let imageLoadingInserted = false;

    const flushTextLines = () => {
      const cleaned = textLines.filter((line, index, arr) => !(line === '' && arr[index - 1] === ''));
      if (!cleaned.length) {
        textLines = [];
        return;
      }

      nodes.push({
        type: 'text',
        lines: cleaned.map((line) => ({
          segments: this.parseInlineStyles(line)
        }))
      });
      textLines = [];
    };

    source.split('\n').forEach((rawLine) => {
      if (streaming && imageLoadingInserted) return;

      const line = rawLine || '';
      let lastIndex = 0;
      let hasImage = false;
      let hasFile = false;
      let searchIndex = 0;
      let fileToken;
      let imageToken;

      while ((fileToken = this.extractMarkdownFileToken(line, searchIndex)) !== null) {
        hasFile = true;
        const before = line.slice(lastIndex, fileToken.start).trim();
        if (before) {
          textLines.push(before);
        }

        flushTextLines();
        nodes.push(this.createFileNode(fileToken.url, fileToken.title));

        lastIndex = fileToken.end;
        searchIndex = fileToken.end;
      }

      if (hasFile) {
        const after = line.slice(lastIndex).trim();
        if (after) {
          textLines.push(after);
        }
        return;
      }

      while ((imageToken = this.extractMarkdownImageToken(line, searchIndex)) !== null) {
        hasImage = true;
        const before = line.slice(lastIndex, imageToken.start).trim();
        if (before) {
          textLines.push(before);
        }

        flushTextLines();
        this.splitImageUrls(imageToken.url).forEach((url) => {
          nodes.push({
            type: 'image',
            alt: imageToken.alt || '图片',
            url
          });
        });

        lastIndex = imageToken.end;
        searchIndex = imageToken.end;
      }

      const remainingText = hasImage ? line.slice(lastIndex) : line;
      if (streaming) {
        const incompleteImageIndex = this.findIncompleteImageStart(remainingText);
        if (incompleteImageIndex >= 0) {
          const before = remainingText.slice(0, incompleteImageIndex).trim();
          if (before) {
            textLines.push(before);
          }

          flushTextLines();
          nodes.push(this.createLoadingNode('image'));
          imageLoadingInserted = true;
          return;
        }
      }

      if (!hasImage) {
        const directFileTokens = this.extractDirectFileUrlTokens(line);
        if (directFileTokens.length) {
          let cursor = 0;
          directFileTokens.forEach((token) => {
            const before = line.slice(cursor, token.start).trim();
            if (before) {
              textLines.push(before);
            }

            flushTextLines();
            nodes.push(this.createFileNode(token.url, token.title));
            cursor = token.end;
          });

          const after = line.slice(cursor).trim();
          if (after) {
            textLines.push(after);
          }
          return;
        }

        const directImageTokens = this.extractDirectImageUrlTokens(line);
        if (!directImageTokens.length) {
          textLines.push(line);
          return;
        }

        let cursor = 0;
        directImageTokens.forEach((token) => {
          const before = line.slice(cursor, token.start).trim();
          if (before) {
            textLines.push(before);
          }

          flushTextLines();
          this.splitImageUrls(token.url).forEach((url) => {
            nodes.push({
              type: 'image',
              alt: '图片',
              url
            });
          });

          cursor = token.end;
        });

        const after = line.slice(cursor).trim();
        if (after) {
          textLines.push(after);
        }
        return;
      }

      const after = remainingText.trim();
      if (after) {
        textLines.push(after);
      }
    });

    flushTextLines();
    return nodes;
  },

  parseInlineStyles(text) {
    const source = text || '';
    const segments = [];
    const regex = /(\*\*[^*]+\*\*|`[^`]+`)/g;
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(source)) !== null) {
      if (match.index > lastIndex) {
        segments.push({
          text: source.slice(lastIndex, match.index),
          bold: false,
          code: false
        });
      }

      const token = match[0];
      if (token.startsWith('**')) {
        segments.push({
          text: token.slice(2, -2),
          bold: true,
          code: false
        });
      } else {
        segments.push({
          text: token.slice(1, -1),
          bold: false,
          code: true
        });
      }

      lastIndex = regex.lastIndex;
    }

    if (lastIndex < source.length) {
      segments.push({
        text: source.slice(lastIndex),
        bold: false,
        code: false
      });
    }

    return segments.length ? segments : [{ text: source, bold: false, code: false }];
  },

  normalizeTableLine(line) {
    if (!line) return null;
    const trimmed = line.trim();
    if (!trimmed || !trimmed.startsWith('|')) return null;
    return trimmed;
  },

  createLoadingNode(kind) {
    return {
      type: `${kind}_loading`,
      label: kind === 'image' ? '图片解析中' : '表格解析中'
    };
  },

  extractMarkdownImageToken(text, fromIndex = 0) {
    const source = text || '';
    const start = source.indexOf('![', fromIndex);
    if (start < 0) return null;

    const altStart = start + 2;
    const altEnd = source.indexOf('](', altStart);
    if (altEnd < 0) return null;

    let cursor = altEnd + 2;
    let nestedDepth = 0;
    let inAngleUrl = false;

    while (cursor < source.length) {
      const char = source[cursor];

      if (!inAngleUrl && char === '<' && nestedDepth === 0) {
        inAngleUrl = true;
        cursor += 1;
        continue;
      }

      if (inAngleUrl && char === '>') {
        inAngleUrl = false;
        cursor += 1;
        continue;
      }

      if (!inAngleUrl && char === '(') {
        nestedDepth += 1;
        cursor += 1;
        continue;
      }

      if (!inAngleUrl && char === ')') {
        if (nestedDepth === 0) {
          let url = source.slice(altEnd + 2, cursor).trim();
          if (url.startsWith('<') && url.endsWith('>')) {
            url = url.slice(1, -1).trim();
          }

          return {
            start,
            end: cursor + 1,
            alt: source.slice(altStart, altEnd).trim(),
            url
          };
        }

        nestedDepth -= 1;
      }

      cursor += 1;
    }

    return null;
  },

  splitImageUrls(value) {
    const source = String(value || '').trim();
    if (!source) {
      return [];
    }

    const parts = source
      .split(/(?:\r?\n)+|(?:\s*[；;]\s*)(?=https?:\/\/)/i)
      .map((item) => item.trim())
      .filter(Boolean);

    return parts.length ? parts : [source];
  },

  normalizeUrlCandidate(value) {
    let url = String(value || '').trim();
    if (!url) return '';

    if (url.startsWith('<') && url.endsWith('>')) {
      url = url.slice(1, -1).trim();
    }

    while (/[)>\]。，；、，]$/.test(url)) {
      url = url.slice(0, -1).trim();
    }

    return url;
  },

  isLikelyImageUrl(value) {
    const url = this.normalizeUrlCandidate(value);
    if (!/^https?:\/\//i.test(url)) {
      return false;
    }

    return /\.(png|jpe?g|webp|gif|bmp)(?:[?#].*)?$/i.test(url);
  },

  getFileTypeFromUrl(value) {
    const url = this.normalizeUrlCandidate(value);
    const path = url.split(/[?#]/)[0] || '';
    const match = path.match(/\.([a-z0-9]+)$/i);
    const extension = match ? match[1].toLowerCase() : '';
    const supportedTypes = new Set(['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx']);
    return supportedTypes.has(extension) ? extension : '';
  },

  isLikelyFileUrl(value) {
    const url = this.normalizeUrlCandidate(value);
    return /^https?:\/\//i.test(url) && !!this.getFileTypeFromUrl(url);
  },

  createFileNode(url, title = '') {
    const cleanUrl = this.normalizeUrlCandidate(url);
    const fileType = this.getFileTypeFromUrl(cleanUrl);
    const fallbackName = this.extractFileNameFromUrl(cleanUrl);
    return {
      type: 'file',
      title: String(title || '').trim() || fallbackName || '文件',
      fileName: fallbackName || String(title || '').trim() || '文件',
      fileType,
      url: cleanUrl
    };
  },

  extractFileNameFromUrl(value) {
    const url = this.normalizeUrlCandidate(value);
    if (!url) return '';

    try {
      const path = url.split(/[?#]/)[0] || '';
      const filename = path.split('/').filter(Boolean).pop() || '';
      return decodeURIComponent(filename) || filename;
    } catch (err) {
      const path = url.split(/[?#]/)[0] || '';
      return path.split('/').filter(Boolean).pop() || '';
    }
  },

  extractMarkdownFileToken(text, fromIndex = 0) {
    const source = text || '';
    let cursor = Math.max(0, fromIndex);

    while (cursor < source.length) {
      const start = source.indexOf('[', cursor);
      if (start < 0) return null;

      if (source[start - 1] === '!') {
        cursor = start + 1;
        continue;
      }

      const titleEnd = source.indexOf('](', start + 1);
      if (titleEnd < 0) return null;

      let urlCursor = titleEnd + 2;
      let nestedDepth = 0;
      let inAngleUrl = false;

      while (urlCursor < source.length) {
        const char = source[urlCursor];

        if (!inAngleUrl && char === '<' && nestedDepth === 0) {
          inAngleUrl = true;
          urlCursor += 1;
          continue;
        }

        if (inAngleUrl && char === '>') {
          inAngleUrl = false;
          urlCursor += 1;
          continue;
        }

        if (!inAngleUrl && char === '(') {
          nestedDepth += 1;
          urlCursor += 1;
          continue;
        }

        if (!inAngleUrl && char === ')') {
          if (nestedDepth === 0) {
            let url = source.slice(titleEnd + 2, urlCursor).trim();
            if (url.startsWith('<') && url.endsWith('>')) {
              url = url.slice(1, -1).trim();
            }

            if (this.isLikelyFileUrl(url)) {
              return {
                start,
                end: urlCursor + 1,
                title: source.slice(start + 1, titleEnd).trim(),
                url
              };
            }

            break;
          }

          nestedDepth -= 1;
        }

        urlCursor += 1;
      }

      cursor = start + 1;
    }

    return null;
  },

  extractDirectImageUrlTokens(line) {
    const source = String(line || '');
    if (!source) {
      return [];
    }

    const tokens = [];
    const urlRegex = /https?:\/\/[^\s]+/gi;
    let match;

    while ((match = urlRegex.exec(source)) !== null) {
      const rawUrl = match[0];
      const normalizedUrl = this.normalizeUrlCandidate(rawUrl);
      if (!this.isLikelyImageUrl(normalizedUrl)) {
        continue;
      }

      tokens.push({
        start: match.index,
        end: match.index + rawUrl.length,
        url: normalizedUrl
      });
    }

    return tokens;
  },

  extractDirectFileUrlTokens(line) {
    const source = String(line || '');
    if (!source) {
      return [];
    }

    const tokens = [];
    const urlRegex = /https?:\/\/[^\s]+/gi;
    let match;

    while ((match = urlRegex.exec(source)) !== null) {
      const rawUrl = match[0];
      const normalizedUrl = this.normalizeUrlCandidate(rawUrl);
      if (!this.isLikelyFileUrl(normalizedUrl)) {
        continue;
      }

      tokens.push({
        start: match.index,
        end: match.index + rawUrl.length,
        url: normalizedUrl,
        title: this.extractFileNameFromUrl(normalizedUrl)
      });
    }

    return tokens;
  },

  findIncompleteImageStart(text) {
    if (!text) return -1;
    return text.indexOf('![');
  },

  isMarkdownTableRow(line) {
    const normalized = this.normalizeTableLine(line);
    if (!normalized) return false;
    return (normalized.match(/\|/g) || []).length >= 2;
  },

  isPotentialMarkdownTableRow(line) {
    const trimmed = (line || '').trim();
    if (!trimmed) return false;
    return trimmed.startsWith('|');
  },

  isTableSeparatorLine(line) {
    const normalized = this.normalizeTableLine(line);
    if (!normalized) return false;
    const cells = this.splitTableRow(normalized);
    return !!cells.length && cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s/g, '')));
  },

  shouldShowTableLoading(lines) {
    if (!lines || !lines.length) return false;
    if (!this.isPotentialMarkdownTableRow(lines[0])) return false;
    if (lines.length === 1) return true;
    if (this.isTableSeparatorLine(lines[1])) return true;
    return lines.some((line) => this.isPotentialMarkdownTableRow(line));
  },

  isMarkdownImage(line) {
    return !!this.extractMarkdownImageToken(line);
  },

  hasRenderableImage(line) {
    return (
      this.isMarkdownImage(line) ||
      this.extractDirectImageUrlTokens(line).length > 0 ||
      !!this.extractMarkdownFileToken(line) ||
      this.extractDirectFileUrlTokens(line).length > 0
    );
  },

  parseMarkdownTable(lines) {
    if (!lines || lines.length < 2) return null;

    const headers = this.splitTableRow(lines[0]);
    const separator = this.splitTableRow(lines[1]);

    if (
      !headers.length ||
      !separator.length ||
      !separator.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s/g, '')))
    ) {
      return null;
    }

    const rows = lines
      .slice(2)
      .map((line) => this.splitTableRow(line))
      .filter((row) => row.length);

    if (!rows.length) return null;

    const width = headers.length;
    return {
      type: 'table',
      headers: headers.map((header, index) => ({
        cellIndex: index,
        text: header
      })),
      rows: rows.map((row, rowIndex) => {
        const cells = row.slice(0, width);
        while (cells.length < width) {
          cells.push('-');
        }

        return {
          rowIndex,
          cells: cells.map((cell, cellIndex) => ({
            cellIndex,
            text: cell === '' ? '-' : cell
          }))
        };
      })
    };
  },

  splitTableRow(line) {
    return (line || '')
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((cell) => cell.trim());
  },

  previewImage(e) {
    const current = e.currentTarget.dataset.url;
    if (!current) return;

    const urls = [];
    this.data.messages.forEach((message) => {
      (message.displayNodes || []).forEach((node) => {
        if (node.type === 'image' && node.url) {
          urls.push(node.url);
        }
      });
    });

    wx.previewImage({
      current,
      urls: urls.length ? urls : [current]
    });
  },

  openFileCard(e) {
    const dataset = (e && e.currentTarget && e.currentTarget.dataset) || {};
    const url = dataset.url;
    const fileType = dataset.filetype || this.getFileTypeFromUrl(url) || 'pdf';
    const title = dataset.title || dataset.filename || '文件';

    if (!url) {
      wx.showToast({ title: '文件链接为空', icon: 'none' });
      return;
    }

    wx.showLoading({ title: '正在下载' });

    // 云存储 fileID：直接通过 wx.cloud 下载（不经后端）
    if (url.startsWith('cloud://')) {
      wx.cloud.downloadFile({
        fileID: url,
        success: (res) => {
          this.openDownloadedDocument(res.tempFilePath, fileType, title);
        },
        fail: (err) => {
          wx.hideLoading();
          console.warn('cloud downloadFile failed:', err);
          wx.showToast({ title: '下载失败，请稍后重试', icon: 'none' });
        },
      });
      return;
    }

    // 普通 https 链接：分片下载，避免 downloadFile 合法域名限制、
    // COS 临时签名过期，以及 callContainer 返回包 1MB 上限问题。
    const token = app.globalData.token || wx.getStorageSync('token') || '';
    const CHUNK = 786 * 1024; // 与后端 CHUNK_SIZE 一致
    const fileName = this.extractFileNameFromUrl(url) || '文件';
    const basePath = `/api/samples/download?url=${encodeURIComponent(url)}&filename=${encodeURIComponent(fileName)}`;

    const cc = (extraPath) => new Promise((resolve, reject) => {
      wx.cloud.callContainer({
        config: app.getCallContainerConfig(),
        path: basePath + extraPath,
        method: 'GET',
        timeout: 15000, // callContainer timeout 上限 15s，超出无效
        responseType: 'arraybuffer',
        header: app.buildServiceHeaders({
          'Authorization': `Bearer ${token}`,
        }),
        success: resolve,
        fail: reject,
      });
    });

    const decodeErrorMsg = (res) => {
      if (res && res.data) {
        try {
          const bytes = new Uint8Array(res.data);
          let text = '';
          const c = 8192;
          for (let i = 0; i < bytes.length; i += c) {
            text += String.fromCharCode.apply(null, bytes.subarray(i, i + c));
          }
          const json = JSON.parse(text);
          if (json && json.detail && typeof json.detail === 'string') {
            return json.detail;
          }
        } catch (e) {
          /* 解析失败则使用默认提示 */
        }
      }
      return '';
    };

    const fetchPart = async (part, parts) => {
      let lastErr = null;
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const partRes = await cc(`&action=download&part=${part}&part_size=${CHUNK}`);
          if (partRes.statusCode === 200 && partRes.data) {
            return new Uint8Array(partRes.data);
          }
          lastErr = decodeErrorMsg(partRes) || `下载片段 ${part + 1}/${parts} 失败`;
        } catch (err) {
          lastErr = '网络异常，请重试';
          console.warn(`download part ${part} attempt ${attempt + 1} failed:`, err);
        }
      }
      throw new Error(lastErr || '下载失败，请稍后重试');
    };

    (async () => {
      try {
        // 1) 先获取文件大小与分片数
        const metaRes = await cc('&action=meta');
        if (metaRes.statusCode !== 200 || !metaRes.data) {
          throw new Error(decodeErrorMsg(metaRes) || '获取文件信息失败');
        }
        const meta = JSON.parse(decodeErrorMsg(metaRes) || '{}') || {};
        const total = meta.size;
        const parts = meta.parts;
        if (!total || !parts) {
          throw new Error('文件为空，无法下载');
        }

        // 2) 按分片顺序拉取并拼接
        const buffer = new Uint8Array(total);
        for (let i = 0; i < parts; i += 1) {
          const chunkBytes = await fetchPart(i, parts);
          buffer.set(chunkBytes, i * CHUNK);
          if (i > 0 && i % 10 === 0) {
            wx.showLoading({ title: `下载中 ${i}/${parts}` });
          }
        }

        // 3) 写临时文件后打开
        const tempFilePath = `${wx.env.USER_DATA_PATH}/${Date.now()}_${fileName}`;
        wx.getFileSystemManager().writeFile({
          filePath: tempFilePath,
          data: buffer.buffer,
          encoding: 'binary',
          success: () => {
            this.openDownloadedDocument(tempFilePath, fileType, title);
          },
          fail: (err) => {
            wx.hideLoading();
            console.warn('write file failed:', err);
            wx.showToast({ title: '文件保存失败', icon: 'none' });
          },
        });
      } catch (err) {
        wx.hideLoading();
        const msg = (err && err.message) ? err.message : '下载失败，请稍后重试';
        console.warn('proxy download failed:', err);
        wx.showToast({ title: msg.length > 20 ? msg.slice(0, 20) : msg, icon: 'none' });
      }
    })();
  },

  openDownloadedDocument(filePath, fileType, title) {
    wx.openDocument({
      filePath,
      fileType,
      showMenu: true,
      success: () => {
        wx.hideLoading();
      },
      fail: (err) => {
        wx.hideLoading();
        console.warn('openDocument failed:', err);
        wx.showToast({ title: `无法打开${title}`, icon: 'none' });
      },
    });
  },

  onShareAppMessage() {
    return {};
  }
});
