const { useState, useEffect, useRef } = React;

const movies = [
  { id: 'A', name: 'Interstellar', rating: '8.6/10', genre: 'Sci-Fi', description: 'A team of explorers travel through a wormhole in space in an attempt to ensure humanity\'s survival.', image: '../assets/img_1.png' },
  { id: 'B', name: 'Inception', rating: '8.8/10', genre: 'Action/Sci-Fi', description: 'A thief who steals corporate secrets through the use of dream-sharing technology.', image: '../assets/img_2.png' }
];

function useEventLogger() {
  const startTime = useRef(null);
  const startTask = () => startTime.current = performance.now();
  
  const logEvent = async (participant_id, condition, decision) => {
    const latency_ms = startTime.current ? performance.now() - startTime.current : 0;
    fetch('http://localhost:8000/api/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ participant_id, condition, decision, timestamp: new Date().toISOString(), latency_ms })
    }).catch(e => console.error(e));
  };
  return { startTask, logEvent };
}

function TaskCard({ name, rating, genre, description, image, onSelect, buttonText }) {
  return (
    <div className="task-card">
      <img src={image} alt={name} className="movie-image" />
      <div className="movie-details">
        <h3>{name}</h3>
        <p><strong>Rating:</strong> {rating}</p>
        <p><strong>Genre:</strong> {genre}</p>
        <p className="description">{description}</p>
      </div>
      <button onClick={onSelect} className={buttonText === 'Choose AI Recommendation' ? 'ai-select-btn' : 'normal-btn'}>{buttonText}</button>
    </div>
  );
}

function App() {
  const [pid, setPid] = useState('');
  const [condition, setCondition] = useState('');
  const [started, setStarted] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [recommendedMovie] = useState(() => movies[Math.floor(Math.random() * movies.length)]);
  const { startTask, logEvent } = useEventLogger();

  useEffect(() => {
    const searchParams = new URLSearchParams(window.location.search);
    let currentPid = searchParams.get('pid');
    
    if (!currentPid) {
      currentPid = Math.floor(Math.random() * 90000 + 10000).toString() + Date.now().toString().slice(-3);
      window.history.replaceState(null, '', `?pid=${currentPid}`);
    }
    
    setPid(currentPid);
    const lastDigit = parseInt(currentPid.slice(-1), 10);
    setCondition(lastDigit % 2 === 0 ? 'A' : 'B');
  }, []);

  const handleStart = () => {
    setStarted(true);
    startTask();
  };

  const handleDecision = async (decisionId) => {
    await logEvent(pid, condition, decisionId);
    setCompleted(true);
  };

  if (completed) return <div className="container center"><h2>Thank you for your participation</h2></div>;

  if (!started) {
    return (
      <div className="container center">
        <h2>Welcome to the Study</h2>
        <p>Participant ID: {pid || 'Generating...'}</p>
        <p>Please review the details and click start to begin the task.</p>
        <button onClick={handleStart}>Start Task</button>
      </div>
    );
  }

  const isAgentA = condition === 'A';
  const agentName = isAgentA ? 'System AI' : 'Alex';
  const recommendationText = isAgentA ? `I suggest ${recommendedMovie.name} with 92% confidence.` : `Based on your viewing history, you might like ${recommendedMovie.name}.`;

  return (
    <div className="container">
      <div className="agent-cue">
        <h3>{agentName} recommends:</h3>
        <p>"{recommendationText}"</p>
      </div>
      <div className="movie-options">
        {movies.map(movie => {
          const isRecommended = movie.id === recommendedMovie.id;
          const btnText = isRecommended ? "Choose AI Recommendation" : "Select this product";
          return <TaskCard key={movie.id} {...movie} onSelect={() => handleDecision(movie.id)} buttonText={btnText} />;
        })}
      </div>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
