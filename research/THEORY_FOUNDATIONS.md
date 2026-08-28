# “理解成本工具”理论根基与论文审计

> 版本：研究草案 v0.3
> 日期：2026-08-26
> 状态：理论审计基线；Demo Skill 已另行建立，但本文中的综合公式与假设仍未完成效度验证

> **Demo 决策说明**：在本审计完成后，用户明确决定现有根基足以先建立一个可证伪 Demo。Demo 只固化证据较强的流程边界；学习响应画像与三维 Focus Cone 均按实验假设保存，不宣称为学界定论。

> **全文准入规则**：本报告的有效证据只保留可免登录直接阅读全文的期刊 HTML、期刊 PDF、作者稿、大学或公共学术机构仓储版本。只有 DOI、摘要、书籍预览、付费墙、需申请或登录下载的文献，不进入论证链。链接优先指向全文本身，而不是 DOI 落地页。

## 1. 结论先行

你的理论**有足够坚实的相邻研究基础，值得继续立项**，但目前不存在一篇论文已经定义并验证了你设想的完整“理解成本”指标。

最直接的理论根基是 Knowledge Space Theory / Learning Space Theory（知识空间 / 学习空间理论）：它把某一明确领域中个体可能具备的知识集合建模为 `knowledge state`，并进一步定义 `inner fringe` 和 `outer fringe`。其中 `outer fringe` 表示从当前知识状态出发、下一步已经准备好学习的项目。这与“知识网络内、边界、网络外”的直觉高度对应，但不是欧氏圆形距离，也不能直接由 Obsidian 链接图推出。

现有研究能够较强支持：

- 学习路径应由“特定学习者 × 特定知识或任务 × 目标能力”共同决定；
- 先验知识会改变材料的实际难度，也会改变合适的辅助强度；
- 前置关系、知识组件、动态掌握状态可以被形式化建模；
- 媒介和教学方式应随知识类型、目标表现、动态性及反馈需要变化；
- “真正掌握”应通过独立表现、保持和迁移证据推断，而不能由“听懂了”或一次答对确认；
- 优化目标应是达到长期保持与迁移标准所需的预计总成本，而非本次解释最短或当下感觉最轻松。

目前没有充分证据直接支持：

- 把所有理解成本压成一个已经有公认权重的总分；
- 把知识图中的节点度数直接等同于理解成本；
- 仅凭一次对话准确确定用户在整个领域的知识边界；
- 用固定规则把“知识类型”直接映射成文字、视频或对话；
- 把 Obsidian 全局图当作人的真实认知网络；
- 把先前讨论的 L0–L6 理解等级当成已验证量表。

因此在研究审计阶段，应先产出“构念定义 + 测量规范 + 小规模验证方案”。用户审阅根基后已授权把其中证据较强的边界固化为 Demo Skill；尚未验证的学习响应画像、成本比较与 Focus Cone 仍必须以可证伪假设运行，不能因已写入 Skill 就升级为定论。

## 2. 需要建模的对象

推荐把分析单位写成：

> `学习者 × 目标知识/任务 × 目标能力 × 使用情境 × 时间跨度`

其中有两条彼此独立的入口轴：

1. **范围轴**：单个知识点 / 局部知识簇 / 整体领域地图；
2. **结果轴**：定位 / 解释 / 执行 / 迁移。

“知识点还是整体地图”只描述范围，不能替代对学习终点的判断。同一个知识点，用户可能只想知道它的位置，也可能要能独立操作或在新情境中迁移，成本会完全不同。

## 3. 命题—证据—边界矩阵

| 你的命题 | 证据判断 | 主要论文 | 能支持什么 | 不能推出什么 |
|---|---|---|---|---|
| 需要识别用户的知识边界 | 强支持，但必须限定领域 | [Doignon & Falmagne：全文 PDF](https://arxiv.org/pdf/1511.06757) | 可在明确题目或技能域中表示可能的 `knowledge state` | 不能凭少量闲聊确定一个人的“全部知识边界” |
| 找到用户已掌握且最接近目标的知识 | 强支持 | [Doignon & Falmagne：全文 PDF](https://arxiv.org/pdf/1511.06757) | `outer fringe` 可形式化“前置已满足、当前准备好学习的下一项” | 语义相似的最近邻不一定满足先修条件 |
| 网络内、边缘、网络外需采用不同策略 | 强支持，可比原三分法更精确 | [Doignon & Falmagne：全文 PDF](https://arxiv.org/pdf/1511.06757) | 可以区分知识状态、内边缘、外边缘及尚被前置条件阻塞的项目 | 不是圆形几何距离；网络外也不是单一状态 |
| 每个人需要不同前置知识和学习路径 | 强支持 | [KLI framework：ERIC 全文 PDF](https://files.eric.ed.gov/fulltext/ED535880.pdf) | 可围绕知识组件、学习事件和目标表现选择不同教学动作 | 不存在跨领域都可直接计算的唯一最短路径 |
| 更难的知识可能对某个人成本更低 | 强支持 | [先验知识元分析：大学机构库全文 PDF](https://www.uni-trier.de/fileadmin/fb1/prof/PSY/PAE/Team/Schneider/SimonsmeierEtAl2021.pdf)；[知识反转效应元分析：peDOCS 全文 PDF](https://www.pedocs.de/volltexte/2026/34113/pdf/Learn_and_Instr_2025_Tetzlaff_u.a._A_cornerstone_of_adaptivity.pdf) | 先验知识能帮助解释、组块和检索；高辅助对新手有利，对高知识者可能冗余 | 不能只用知识点的客观“难度”预测个人成本 |
| 关联越多，理解成本越高 | 仅部分支持，原表述需否定 | [Chen, Paas & Sweller：出版社开放全文](https://link.springer.com/article/10.1007/s10648-023-09782-w) | 必须同时处理的交互元素越多，任务复杂度可能越高；元素交互性取决于材料与学习者长时记忆的组合 | 节点度数不是成本；已知连接可成为锚点并降低成本 |
| 先验知识决定后续学习表现 | 强支持但不是简单线性关系 | [Simonsmeier et al.：全文 PDF](https://www.uni-trier.de/fileadmin/fb1/prof/PSY/PAE/Team/Schneider/SimonsmeierEtAl2021.pdf) | 先验知识与后测水平稳定相关，也可能通过组块、解释、误概念或干扰等不同路径影响学习 | “知道得越多就必然学得越快”不成立；其元分析中先验知识与标准化增益的平均关系很小且高度异质 |
| 应动态判断用户是否掌握 | 强支持 | [Corbett & Anderson：大学课程库全文 PDF](https://perso.liris.cnrs.fr/pierre-antoine.champin/2014/m2iade-ia2/_static/893CorbettAnderson1995.pdf)；[Knowledge Tracing Survey：arXiv 全文 PDF](https://arxiv.org/pdf/2201.06953)；[Evidence-Centered Design：CRESST 全文 PDF](https://cresst.org/wp-content/uploads/R632.pdf) | 掌握是潜变量，需要把任务表现当证据并持续更新估计 | KT 的答题预测准确率本身不等于深度理解或迁移有效性 |
| 整体地图需要关系网、树等多种形式 | 中强支持 | [概念图元分析：SFU 全文 PDF](https://www.sfu.ca/~jcnesbit/research/NesbitAdesope2006.pdf)；[多外部表征元分析：出版社开放全文](https://link.springer.com/article/10.1007/s10648-024-09958-y) | 概念图总体上有助学习；不同表征可以互补 | 增加表征也会引入映射和协调成本；不是越多越好 |
| 视频、文字和交互方式应随任务改变 | 较强、有边界 | [视频交互元分析：期刊全文 PDF](https://aver.nwnu.edu.cn/upload/formalarticle/202407/2024070228-%E8%A7%86%E9%A2%91%E4%B8%AD%E7%9A%84%E4%BA%A4%E4%BA%92%E8%AE%BE%E8%AE%A1%E5%8F%AF%E4%BB%A5%E4%BF%83%E8%BF%9B%E5%AD%A6%E4%B9%A0%E5%90%97%EF%BC%9F%20%E2%80%94%E2%80%94%E5%9F%BA%E4%BA%8E53%E9%A1%B9%E5%AE%9E%E9%AA%8C%E4%B8%8E%E5%87%86%E5%AE%9E%E9%AA%8C%E7%9A%84%E5%85%83%E5%88%86%E6%9E%90.pdf)；[通道效应元分析：期刊全文 PDF](https://journal.psych.ac.cn/xlkxjz/CN/article/downloadArticleFile.do?attachType=PDF&id=3446) | 交互、步调、材料动态性、先验知识和目标测验会调节效果 | 不能推出“视频总比文字好”或“复杂知识一定用视频” |
| 复杂概念可用对话促进理解 | 有支持，但支持的是结构化自我解释与反馈 | [Chi et al.：ERIC 全文报告](https://files.eric.ed.gov/fulltext/ED296291.pdf)；[朱怡、胡谊：期刊 RichHTML 全文](https://journal.psych.ac.cn/xlxb/CN/10.3724/SP.J.1041.2024.00555) | 解释理由、条件和步骤，或提供有组织的纠错反馈，可能促进结构理解与迁移 | Chi 研究样本很小且限于物理例题；不能把任意聊天等同于有效教学对话 |
| 应按用户自称的学习风格选择视频或文字 | 证据反对 | [Pashler et al.：UCLA 作者实验室全文 PDF](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/07/Pashler_McDaniel_Rohrer_Bjork_2009_PSPI.pdf) | 可以把偏好作为体验因素 | 没有可靠证据证明按“视觉型/听觉型”匹配媒介能提高学习效果 |
| 掌握要通过主动提取、保持和迁移判断 | 强支持 | [周爱保等：期刊全文 PDF](https://journal.psych.ac.cn/xlxb/CN/article/downloadArticleFile.do?attachType=PDF&id=3548)；[Soderstrom & Bjork：UCLA 全文 PDF](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/11/soderstorm_ra_learningvsperformance.pdf)；[朱怡、胡谊：期刊全文](https://journal.psych.ac.cn/xlxb/CN/10.3724/SP.J.1041.2024.00555) | 提取练习支持保持和迁移；即时表现与长期学习必须区分；延迟迁移应进入验证标准 | 一次原题答对不能证明独立掌握或远迁移 |
| 每个知识点存在固定的“最少信息” | 仅部分支持 | [KLI framework：ERIC 全文 PDF](https://files.eric.ed.gov/fulltext/ED535880.pdf) | 可以围绕目标任务分解知识组件和评估事件 | 不存在脱离目标能力、学习者与情境的固定最小字数或节点数 |
| 理解时间应降至最低 | 方向支持，目标需改写 | [Soderstrom & Bjork：UCLA 全文 PDF](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/11/soderstorm_ra_learningvsperformance.pdf) | 应优化达到长期学习标准的总投入，而不是只追求当下流畅 | 当下更快、更轻松不一定产生更好的保持或迁移 |

## 4. 中文论文证据链

下面把中文研究单列。这里的每个标题都指向期刊官网或官方机构的直达全文；未取得全文的中文来源已删除。

### 4.1 认知负荷、先验知识与知识反转

1. 张冬梅、路海东、祖雅桐（2016）。[《认知负荷视角下的知识反转效应》（全文 PDF）](https://journal.psych.ac.cn/xlkxjz/CN/article/downloadArticleFile.do?attachType=PDF&id=3462)。《心理科学进展》，24(4)，501–509。
   证据类型：理论综述。支持“教学帮助应随先备知识变化”；不能作为本项目成本公式的直接验证。

2. 李金波、许百华（2009）。[《人机交互过程中认知负荷的综合测评方法》（全文 PDF）](https://journal.psych.ac.cn/xlxb/CN/article/downloadArticleFile.do?attachType=PDF&id=3217)。《心理学报》，41(1)，35–43。
   证据类型：双任务实验与多指标建模。主观评定、绩效和眼动等指标的综合测量优于单一指标；支持本项目先保留成本向量，不能证明该论文的特定模型可跨学习领域直接迁移。

3. 朱怡、胡谊（2024）。[《师生互动中组块化反馈促进长时学习迁移：行为和近红外超扫描研究》（RichHTML 全文）](https://journal.psych.ac.cn/xlxb/CN/10.3724/SP.J.1041.2024.00555)。《心理学报》，56(5)，555–576。
   证据类型：两项师生双人实验。组块化反馈促进低先验知识学生的长时迁移，且错误修正起中介作用；这是特定互动任务中的结果，不能泛化为“信息越分块越好”。

4. 周爱保、马小凤、李晶、崔丹（2013）。[《提取练习在记忆保持与迁移中的优势效应：基于认知负荷理论的解释》（全文 PDF）](https://journal.psych.ac.cn/xlxb/CN/article/downloadArticleFile.do?attachType=PDF&id=3548)。《心理学报》，45(8)，849–859。
   证据类型：两项实验。发现先前知识与学习策略存在交互，概念图策略更依赖先前知识；支持“策略成本因人而异”，但不能证明所有领域都应优先使用提取练习。

### 4.2 多媒体、线索与表征方式

5. 王福兴、谢和平、李卉（2016）。[《视觉单通道还是视听双通道？——通道效应的元分析》（全文 PDF）](https://journal.psych.ac.cn/xlkxjz/CN/article/downloadArticleFile.do?attachType=PDF&id=3446)。《心理科学进展》，24(3)，335–350。
   证据类型：元分析，91 篇研究。视听双通道对保持和迁移的平均优势较小但显著，并受步调、动态性和时长调节；不能推出“视频总比文字好”。

6. 谢和平、王福兴、周宗奎、吴鹏（2016）。[《多媒体学习中线索效应的元分析》（全文 PDF）](https://journal.psych.ac.cn/xlxb/CN/article/downloadArticleFile.do?attachType=PDF&id=3368)。《心理学报》，48(5)，540–555。
   证据类型：元分析，43 篇研究。线索提高保持和迁移并引导注意，但效应受线索类型、材料动态性和知识类型调节；支持“媒介内部还需要注意引导设计”。

7. 王燕青、王福兴、谢和平、陈佳雪、李文静、胡祥恩（2019）。[《一图抵千言：多媒体学习中的自我生成绘图策略》（全文 PDF）](https://journal.psych.ac.cn/xlkxjz/CN/article/downloadArticleFile.do?attachType=PDF&id=4653)。《心理科学进展》，27(4)，623–635。
   证据类型：综述。绘图可能促进心理模型建构，也可能因操作本身增加负荷；直接反对“凡是知识地图都天然降低成本”。

8. 杨九民、章仪、杨荣华、皮忠玲（2023）。[《想象策略能促进多媒体的学习么？元分析的视角》（全文 PDF）](https://journal.psych.ac.cn/xlkxjz/CN/article/downloadArticleFile.do?attachType=PDF&id=6979)。《心理科学进展》，31(12)，2263–2274。
   证据类型：元分析，20 篇论文、65 个效应量。想象策略提高保持、理解和迁移，但没有显著降低学习时间或认知负荷；说明“效果更好”与“成本更低”必须分开测量。

9. 杨九民、何静、章仪、汪洋、皮忠玲（2024）。[《视频中的交互设计可以促进学习吗？——基于53项实验与准实验的元分析》（全文 PDF）](https://aver.nwnu.edu.cn/upload/formalarticle/202407/2024070228-%E8%A7%86%E9%A2%91%E4%B8%AD%E7%9A%84%E4%BA%A4%E4%BA%92%E8%AE%BE%E8%AE%A1%E5%8F%AF%E4%BB%A5%E4%BF%83%E8%BF%9B%E5%AD%A6%E4%B9%A0%E5%90%97%EF%BC%9F%20%E2%80%94%E2%80%94%E5%9F%BA%E4%BA%8E53%E9%A1%B9%E5%AE%9E%E9%AA%8C%E4%B8%8E%E5%87%86%E5%AE%9E%E9%AA%8C%E7%9A%84%E5%85%83%E5%88%86%E6%9E%90.pdf)。《电化教育研究》，2024(7)。
   证据类型：53 项实验与准实验的元分析。交互设计促进多类学习结果，但对认知负荷的总体影响不显著，并受交互类型、先验知识、领域与步调调节；因此“加交互”不是自动降低理解成本。

### 4.3 知识空间、知识图谱与学习路径

10. 姜强、赵蔚、李松、王朋娇（2018）。[《大数据背景下的精准个性化学习路径挖掘研究——基于 AprioriAll 的群体行为分析》（全文 PDF）](https://aver.nwnu.edu.cn/upload/formalarticle/201801/2018011835-%E5%A4%A7%E6%95%B0%E6%8D%AE%E8%83%8C%E6%99%AF%E4%B8%8B%E7%B2%BE%E5%87%86%E4%B8%AA%E6%80%A7%E5%8C%96%E5%AD%A6%E4%B9%A0%E8%B7%AF%E5%BE%84%E6%8C%96%E6%8E%98%E7%A0%94%E7%A9%B6%E2%80%94%E2%80%94%E5%9F%BA%E4%BA%8EAprioriAll%E7%9A%84%E7%BE%A4%E4%BD%93%E8%A1%8C%E4%B8%BA%E5%88%86%E6%9E%90.pdf)。《电化教育研究》，2018(2)。
   证据类型：路径挖掘与应用实验。证明国内已有个性化学习路径的工程探索；其中对“学习风格”的依赖不应被本项目直接继承。

11. 胡学钢、刘菲、卜晨阳（2020）。[《教育大数据中认知跟踪模型研究进展》（全文 PDF）](https://crad.ict.ac.cn/cn/article/pdf/preview/10.7544/issn1000-1239.2020.20190767.pdf)。《计算机研究与发展》，57(12)。
   证据类型：技术综述。确认“可观测答题表现—不可观测知识状态—随时间更新”是成熟建模问题；不能证明模型概率就是心理学意义上的深度理解。

12. 孙建文、栗大智、彭明、邹睿、王佩（2021）。[《从数据视角透析认知追踪：框架、问题及启示》（全文 PDF）](https://openedu.sou.edu.cn/upload/qikanfile/202109161927323073.pdf)。《开放教育研究》，27(5)，99–109。
    证据类型：35 篇论文的数据与框架综述。指出认知追踪存在“重模型、轻数据”和数据处理不一致问题；这正是本工具必须保留原始证据链的理由。

13. 孙建文、周建鹏、刘三女牙、何绯娟、唐云（2021）。[《基于多层注意力网络的可解释认知追踪方法》（全文 PDF）](https://crad.ict.ac.cn/cn/article/pdf/preview/10.7544/issn1000-1239.2021.20210997.pdf)。《计算机研究与发展》，58(12)，2630–2644。
    证据类型：模型与六个基准数据集实验。支持同时利用题目语义关系与历史表现提高可解释性；其指标仍主要是答题预测和模型保真度，而非延迟迁移。

14. 刘坤佳等（2021）。[《可解释深度知识追踪模型》（全文 PDF）](https://crad.ict.ac.cn/cn/article/pdf/preview/10.7544/issn1000-1239.2021.20211021.pdf)。《计算机研究与发展》，58(12)。
    证据类型：可解释知识追踪模型研究。说明知识点关系、历史作答与模型解释可以结合；仍不能把预测准确率当作“理解成本”或稳健掌握的直接效度证据。

### 4.4 对中文证据的总体评价

- 中文心理学期刊中已有质量较高的元分析和原创实验，可直接支撑媒介边界、先验知识交互、提取练习与迁移。
- 中文智能教育研究能支撑知识追踪、图谱和个性化路径的工程可行性，但许多研究优化的是答题预测、满意度或短期成绩，不是本项目所说的长期“理解成本”。
- 部分中文个性化学习研究采用学习风格分类；这类做法与国际综述结论有冲突，不能因为是中文实证就直接继承。
- “中文作者论文”不等于“中国样本研究”。元分析通常汇总多国文献，报告中应始终保留证据类型和样本边界。
- 杨文正、邹霞（2011）、赵国庆等（2005）和李艳燕等（2019）目前只核验到摘要或门户页，没有进入本报告的有效证据链。

## 5. 对原理论的必要修订

### 5.1 从一张图改成四层模型

1. **领域知识层**：知识点以及有类型、有方向的关系；
2. **学习者状态层**：每个节点的掌握概率、证据、时间戳、帮助强度、误概念与遗忘风险；
3. **目标子图层**：本次任务真正需要到达的能力和相关节点；
4. **教学动作 / 资源层**：解释、例题、对比、自我解释、视频演示、实践、反馈、测验及预计成本。

Obsidian 图只能充当第一层的粗略材料来源，而且普通双链必须先转换成带语义的关系。至少需要区分：

- 先修关系；
- 组成关系；
- 因果关系；
- 相似 / 类比关系；
- 冲突 / 易混淆关系；
- 应用关系。

### 5.2 从三种位置改成“结构状态 + 证据状态”

结构状态：

- `state`：当前知识状态中的项目；
- `inner fringe`：知识状态的内部边缘；
- `outer fringe`：前置条件已经满足、当前可学的项目；
- `blocked exterior`：尚被未掌握前置条件阻塞的外部项目；
- `out of domain`：超出当前领域模型的项目。

另加一个与结构正交的证据状态：

- `unknown`：尚未测量或证据不足。

如果没有 `unknown`，系统会把“没测过”误判成“不会”。

### 5.3 关系数量不能直接成为成本

需要分别估计：

- `unknown_required_dependencies`：必须同时处理的未知依赖，通常增加成本；
- `known_anchors`：可用来类比、组块和提取的已知连接，可能降低成本；
- `misconception_conflicts`：与现有错误模型冲突的关系，增加纠错成本；
- `transfer_relations`：掌握目标要求覆盖的应用情境，增加验证范围但也提高知识价值。

因此，同样十条边，十个未知前置可能增负荷，十个已知锚点却可能让一个“客观更难”的知识点更容易理解。

### 5.4 媒介选择采用四步链，而非固定映射

> 目标表现 → 学习机制 → 教学动作 → 媒介

例如：

| 目标表现 | 主要机制 / 动作 | 可能媒介 |
|---|---|---|
| 识记与流利度 | 间隔、提取、反馈 | 短文本、卡片、语音均可 |
| 规则归纳 | 对比例题、变式、纠错 | 文字 + 图表 + 互动题 |
| 因果与结构理解 | 自我解释、预测、关系建模 | 对话、概念图、动画，按内容选择 |
| 程序性 / 动作技能 | 可控演示、模仿、实际操作反馈 | 分段视频 + 实践 |
| 迁移与实战 | 新情境任务、诊断、反馈循环 | 案例、模拟、项目任务 |

媒介偏好可以改善体验，但不能充当学习效果的主要决策依据。

### 5.5 整体地图采用协调视图，而非单一力导向图

不同视图解决不同问题：

- 先修 DAG：回答“下一步学什么”；
- 带标签概念图：回答“概念如何关联”；
- 层级树 / 分类表：回答“领域如何分层”；
- 因果图 / 流程图：回答“机制如何运作”；
- 概念 × 能力 / 证据矩阵：回答“掌握标准和缺口在哪里”；
- 全局力导向图：回答“规模、簇和枢纽大致在哪里”。

截图中的 Obsidian 全局图能显示簇、枢纽、桥接点、孤立点和外围节点，适合“全局定位”。但边没有可见类型和方向、外围节点密集且标签缺失，因此它不能单独承担先修诊断、掌握判断或路径推荐。

## 6. “理解成本”的工作定义

建议先把成本保留为向量，而不是立即做加权总分：

\[
\mathbf{C} =
(C_{诊断}, C_{补前置}, C_{核心学习}, C_{练习反馈}, C_{验证}, C_{保持与重学})
\]

每一维都可同时记录：

- 时间；
- 主观 / 行为认知努力；
- 教学交互次数；
- 失败与误判风险。

只有经过数据校准，且明确权重由谁、针对什么目标设定后，才考虑把向量压成标量。

可用的工程化工作定义是：

> 理解成本是在知识状态不确定的条件下，使特定学习者达到预先定义的稳健掌握标准所需的预计诊断、桥接、学习、练习、验证和未来维护成本。

优化问题应写成：

> 在达到指定的独立表现、延迟保持和迁移阈值的约束下，最小化预计总成本。

这不是任何一篇论文现成的公式，而是本项目需要验证的综合性产品假设。

## 7. “掌握”的证据规范

先前设想的 L0–L6 可以继续作为候选产品语言，但目前不应宣称它是心理测量量表。等级必须由可观察证据锚定，并把帮助强度单独记录。

建议证据至少覆盖：

1. 独立解释或独立完成；
2. 边界识别、预测或关键条件判断；
3. 近迁移任务；
4. 错误发现与修正；
5. 延迟提取 / 延迟表现；
6. 必要时的远迁移或后续学习加速。

帮助强度另设 `A0–A4`：从无提示到近乎完整示范。`A3/A4` 下完成不能直接记成独立掌握。

证据链应满足：

> 原始行为证据 → 能力维度判断 → 帮助强度 → 等级 / 概率 → 置信度与状态

不能由语言模型凭对话流畅度虚构“已掌握”“置信度 90%”或并不存在的误概念。

## 8. 可证伪假设

后续原型至少应检验以下假设，而不是只做主观体验测试：

- **H1 预测效度**：成本向量比文本长度、知识点难度和自报熟悉度更能预测达到延迟保持 / 迁移标准所需时间。
- **H2 边缘选路**：基于 `outer fringe` 的下一步推荐比统一课程顺序更快达到同一掌握阈值。
- **H3 关系方向**：未知必需依赖数提高成本，而已知锚点数在控制其他变量后降低成本；原始节点度数不具有稳定单向效应。
- **H4 辅助适配**：低先验知识者从高辅助获益更大，高先验知识者从低冗余辅助获益更大。
- **H5 媒介路由**：基于目标表现和任务动态性的媒介选择，优于基于自报学习风格的媒介匹配。
- **H6 掌握证据**：独立提取 + 迁移 + 延迟证据，比自报“懂了”或一次复述更能预测后续表现。
- **H7 成本不转移**：降低当前解释时间的干预，不会通过增加误概念、未来复习或迁移失败把成本推迟到以后。
- **H8 测量一致性**：核心构念在不同领域、不同熟练度人群中具有可接受的一致性；若不成立，应改为领域专用模型。
- **H9 Focus Cone 增量效度**：在固定掌握合同、通过先修与路线硬约束，并先排除成本 Pareto 被支配方案后，`目标相关性 + 兴趣证据 + 当前软就绪度` 对剩余同层级候选的排序，是否比不使用 Focus 的路线默认顺序更低成本地达到迁移与延迟保持标准。若只提高即时投入或完成速度，却损害保持、迁移或未来重学成本，应判失败。

## 9. Demo 继续迭代与发布前的门槛

在开始写 `SKILL.md` 前，至少完成：

1. 给“理解成本、知识组件、先修、锚点、误概念、掌握、迁移、帮助强度”下操作定义；
2. 选择 1–2 个可控领域做试点，避免一开始声称全领域普适；
3. 建立带类型和方向的领域关系图，并记录每条关键边的来源与可信度；
4. 为候选掌握等级设计可评分的行为任务；
5. 明确延迟长度、迁移距离和停止学习阈值；
6. 用统一顺序、纯 LLM 讲解、文本长度 / 难度基线做对照；
7. 验证工具是否真正降低总成本，而不只是让用户当下感觉更顺；
8. 已写入 Demo 的稳定边界继续保留；未通过效度验证的部分必须标成实验假设，不得作为正式效果承诺发布。

## 10. 推荐的下一份研究产物

下一步不是 Skill，而是：

> `RESEARCH_HYPOTHESES_AND_MEASUREMENT.md`

它应包含构念词典、状态模型、关系类型、诊断题规范、帮助强度、延迟 / 迁移测量、成本记录格式、对照组与通过门槛。完成并审阅后，再决定 Skill 的输入、流程、输出和安全边界。

## 11. 英文核心书目：仅保留全文入口

- Doignon, J.-P., & Falmagne, J.-C. (2015). [Knowledge Spaces and Learning Spaces（arXiv 全文 PDF）](https://arxiv.org/pdf/1511.06757). 这是本项目关于 `knowledge state`、`inner fringe`、`outer fringe` 和学习准备度的最直接根基。
- Koedinger, K. R., Corbett, A. T., & Perfetti, C. (2012). [The Knowledge-Learning-Instruction Framework（ERIC 全文 PDF）](https://files.eric.ed.gov/fulltext/ED535880.pdf). *Cognitive Science, 36*(5), 757–798.
- Chen, O., Paas, F., & Sweller, J. (2023). [A Cognitive Load Theory Approach to Defining and Measuring Task Complexity Through Element Interactivity（出版社开放全文）](https://link.springer.com/article/10.1007/s10648-023-09782-w). *Educational Psychology Review, 35*.
- Simonsmeier, B. A., Flaig, M., Deiglmayr, A., Schalk, L., & Schneider, M. (2021). [Domain-Specific Prior Knowledge and Learning: A Meta-Analysis（大学机构库全文 PDF）](https://www.uni-trier.de/fileadmin/fb1/prof/PSY/PAE/Team/Schneider/SimonsmeierEtAl2021.pdf). *Educational Psychologist*.
- Tetzlaff, L., Simonsmeier, B. A., Peters, T., & Brod, G. (2025). [A Cornerstone of Adaptivity—A Meta-analysis of the Expertise Reversal Effect（peDOCS 全文 PDF）](https://www.pedocs.de/volltexte/2026/34113/pdf/Learn_and_Instr_2025_Tetzlaff_u.a._A_cornerstone_of_adaptivity.pdf). *Learning and Instruction, 98*, 102142.
- Corbett, A. T., & Anderson, J. R. (1995). [Knowledge Tracing: Modeling the Acquisition of Procedural Knowledge（大学课程库全文 PDF）](https://perso.liris.cnrs.fr/pierre-antoine.champin/2014/m2iade-ia2/_static/893CorbettAnderson1995.pdf). *User Modeling and User-Adapted Interaction, 4*, 253–278.
- Abdelrahman, G., Wang, Q., & Nunes, B. P. (2023). [Knowledge Tracing: A Survey（arXiv 全文 PDF）](https://arxiv.org/pdf/2201.06953). *ACM Computing Surveys, 55*(11)*.
- Nesbit, J. C., & Adesope, O. O. (2006). [Learning With Concept and Knowledge Maps: A Meta-Analysis（SFU 全文 PDF）](https://www.sfu.ca/~jcnesbit/research/NesbitAdesope2006.pdf). *Review of Educational Research, 76*(3), 413–448.
- Rexigel, A., et al. (2024). [The More the Better? A Systematic Review and Meta-Analysis of More Than Two External Representations in STEM Education（出版社开放全文）](https://link.springer.com/article/10.1007/s10648-024-09958-y). *Educational Psychology Review, 36*.
- Chi, M. T. H., Bassok, M., Lewis, M. W., Reimann, P., & Glaser, R. (1987). [Self-Explanations: How Students Study and Use Examples in Learning to Solve Problems（ERIC 全文报告）](https://files.eric.ed.gov/fulltext/ED296291.pdf). University of Pittsburgh, Technical Report No. 9.
- Pashler, H., McDaniel, M., Rohrer, D., & Bjork, R. (2009). [Learning Styles: Concepts and Evidence（UCLA 作者实验室全文 PDF）](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/07/Pashler_McDaniel_Rohrer_Bjork_2009_PSPI.pdf). *Psychological Science in the Public Interest, 9*(3), 105–119.
- Soderstrom, N. C., & Bjork, R. A. (2015). [Learning Versus Performance（UCLA 全文 PDF）](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/11/soderstorm_ra_learningvsperformance.pdf). *Perspectives on Psychological Science, 10*(2), 176–199.
- Mislevy, R. J., Almond, R. G., & Lukas, J. F. (2003). [A Brief Introduction to Evidence-Centered Design（CRESST 全文 PDF）](https://cresst.org/wp-content/uploads/R632.pdf). CSE Technical Report 632 / ETS Research Report.
- Clement, B., Roy, D., Oudeyer, P.-Y., & Lopes, M. (2016). [A Contextual Bandits Framework for Personalized Learning Action Selection（EDM 全文 PDF）](https://educationaldatamining.org/EDM2016/proceedings/paper_18.pdf). *Proceedings of EDM 2016*. 它支持把学习者知识状态当情境、在文字/视频/模拟/问题等动作间做探索—利用；其主要目标是下一次评估表现，不能直接证明长期保持或迁移。
- Böck, F., Ochs, M., Henrich, A., et al. (2025). [Learner models: design, components, structure, and modelling—A systematic literature review（开放全文）](https://link.springer.com/article/10.1007/s11257-025-09434-4). 它把 learner model 定义为用于适配学习过程的学习者特征集合，并明确区分 learner model 与 domain model；具体适配仍需行为证据和情境限定。
- Pelánek, R. (2025; online 2024). [Adaptive Learning is Hard: Challenges, Nuances, and Trade-offs in Modeling（开放全文）](https://link.springer.com/article/10.1007/s40593-024-00400-6). 它明确区分 student、domain 与 pedagogical model，并提醒适配存在大量权衡；不能为本项目的圆锥公式提供直接效度。

## 12. 审计边界

- 本报告给出的是文献与产品命题之间的对应关系，不是正式系统综述或注册元分析。
- 有效证据链接只指向可免登录阅读的全文。期刊 RichHTML、开放获取出版社页面、直接 PDF、作者大学主页和公共学术机构仓储均可；DOI 或摘要页本身不算全文。
- 已从有效证据中删除当前未取得合规全文的来源，包括 Doignon & Falmagne（1985）原论文、Falmagne & Doignon（2011）专著、Sweller（2010）、Rafferty 等（2016）、Chi 等（1981）、Ainsworth（2006）、Höffler & Leutner（2007）、Bisra 等（2018）、Barnett & Ceci（2002）、Pavlik & Anderson（2007），以及三篇只找到中文摘要或门户页的论文。
- 删除不表示论文错误，只表示在本次“全文可复核”规则下不能作为当前证据。若以后获得合法免登录全文，可以重新审计后加入。
- 中文论文中已明确区分元分析、实验、综述和工程研究。
- 已核验链接可进入完整正文，但尚未对每篇文献做正式的全文级偏倚评估，也没有计算新的合并效应量。
- 所有“理解成本”公式、状态命名和 H1–H8 都是待检验的工程化综合，不应写成学界定论。
